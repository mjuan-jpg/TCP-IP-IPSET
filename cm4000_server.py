#!/usr/bin/env python3
"""
CM4000 Modbus-TCP Simulator — Main Server
Schneider Electric PowerLogic CM4000 Power Meter Emulator

Usage:
    source .venv/bin/activate
    python cm4000_server.py [--host 0.0.0.0] [--port 5020] [--control-port 5021]

Features:
    • Full register map with Float32 and Mod-10000 encoding
    • Dynamic data with Gaussian noise and load cycling
    • Dedicated Control Port (TCP) for remote event injection
    • Uses pymodbus 3.13 SimDevice API
"""

import sys
import time
import struct
import logging
import asyncio
import argparse
import threading
from typing import Optional

from pymodbus.simulator.simdevice import SimDevice
from pymodbus.simulator.simdata import SimData, DataType
from pymodbus.server import ModbusTcpServer

from cm4000_registers import (
    REGISTER_MAP, REG_BY_NAME, MAX_REGISTER,
    float_to_int16, pf_to_int16, mod10k_to_registers,
)
from cm4000_engine import DataEngine, BaselineProfile, PowerEvent

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("CM4000")

# ─────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║       ⚡  SCHNEIDER ELECTRIC  PowerLogic CM4000  ⚡         ║
║              Modbus-TCP Protocol Simulator                   ║
║                      v1.1.0                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Registers : {reg_count:>4} parameters mapped                       ║
║  Address   : {host}:{port:<5}                                  ║
║  Control   : {host}:{c_port:<5} (Remote Event Injection)       ║
║  Unit ID   : {unit_id:<3}                                            ║
║  Update    : {rate}s cycle                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────
# Shared Register Store (thread-safe)
# ─────────────────────────────────────────────────────────────

class SharedRegisterStore:
    """Thread-safe dict of register address → 16-bit value."""

    def __init__(self):
        self._lock = threading.Lock()
        self._regs: dict[int, int] = {}

    def bulk_update(self, updates: dict[int, int]):
        """Atomically update multiple registers."""
        with self._lock:
            self._regs.update(updates)

    def get_all(self) -> dict[int, int]:
        with self._lock:
            return dict(self._regs)


# Global store — shared between updater thread and async action callback
_store = SharedRegisterStore()


async def _register_action(
    function_code: int,
    start_address: int,
    address: int,
    count: int,
    current_registers: list[int],
    set_values,
):
    """SimDevice action callback — injects live data into every read response."""
    regs = _store.get_all()
    for reg_addr, val in regs.items():
        idx = reg_addr - start_address
        if 0 <= idx < len(current_registers):
            current_registers[idx] = val


# ─────────────────────────────────────────────────────────────
# Register Updater (background thread)
# ─────────────────────────────────────────────────────────────

class RegisterUpdater:
    """Periodically writes DataEngine snapshots into the shared store."""

    def __init__(self, engine: DataEngine, update_rate: float = 1.0):
        self.engine = engine
        self.update_rate = update_rate
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="RegisterUpdater"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        cycle = 0
        while self._running:
            try:
                snapshot = self.engine.snapshot()
                updates = self._encode_snapshot(snapshot)
                _store.bulk_update(updates)

                cycle += 1
                if cycle % 10 == 0:
                    kw = snapshot.get('kW_tot', 0)
                    va = snapshot.get('Vln_avg', 0)
                    ia = snapshot.get('I_avg', 0)
                    freq = snapshot.get('Freq', 0)
                    events = len(self.engine.active_events)
                    log.info(
                        f"Cycle {cycle:>5d} │ "
                        f"V={va:>7.1f}V │ I={ia:>7.1f}A │ "
                        f"P={kw:>7.1f}kW │ f={freq:>5.2f}Hz │ "
                        f"Events={events}"
                    )
            except Exception as e:
                log.error(f"Update error: {e}")
            time.sleep(self.update_rate)

    @staticmethod
    def _encode_snapshot(snapshot: dict) -> dict[int, int]:
        """Convert a snapshot dict into address→u16 register pairs."""
        updates = {}
        for reg_def in REGISTER_MAP:
            value = snapshot.get(reg_def.name)
            if value is None:
                continue
            if reg_def.fmt in ('uint16', 'int16'):
                signed = (reg_def.fmt == 'int16')
                updates[reg_def.address] = float_to_int16(float(value), reg_def.scale, signed)
            elif reg_def.fmt == 'int16_pf':
                updates[reg_def.address] = pf_to_int16(float(value))
            elif reg_def.fmt == 'mod10k':
                regs = mod10k_to_registers(float(value))
                for i, r in enumerate(regs):
                    updates[reg_def.address + i] = r
        return updates


# ─────────────────────────────────────────────────────────────
# Control Server (TCP Event Injection)
# ─────────────────────────────────────────────────────────────

class ControlServer:
    """TCP Server for remote event injection and monitoring."""

    HELP_TEXT = """
┌─────────────────────────────────────────────────────────┐
│  CM4000 Simulator — Remote Control Interface            │
├─────────────────────────────────────────────────────────┤
│  sag <phase> <depth%> <duration_s>                      │
│     → Inject voltage sag (e.g., sag a 30 5)             │
│  swell <phase> <rise%> <duration_s>                     │
│     → Inject voltage swell (e.g., swell b 15 3)         │
│  outage <duration_s>                                    │
│     → Inject full power outage (e.g., outage 10)        │
│  phase_loss <phase> <duration_s>                        │
│     → Drop voltage/current on phase (e.g., phase_loss c 5)│
│  overload <phase> <factor> <duration_s>                 │
│     → Inject current overload (e.g., overload all 1.8 10) │
│  harmonic <phase> <thd_boost%> <duration_s>             │
│     → Inject harmonic spike (e.g., harmonic c 15 5)     │
│  low_pf <pf_value> <duration_s>                         │
│     → Drop power factor (e.g., low_pf 0.50 15)          │
│  pdf                                                    │
│     → (Client) Perfil dinámico de fallas automático     │
│  status                                                 │
│     → Show active events                                │
│  snapshot                                               │
│     → Print current measurements                        │
│  help                                                   │
│     → Show this help                                    │
│  quit / exit                                            │
│     → Close this control session                        │
│  shutdown                                               │
│     → Stop the entire simulator                         │
└─────────────────────────────────────────────────────────┘
"""

    def __init__(self, engine: DataEngine, shutdown_event: threading.Event, host: str, port: int):
        self.engine = engine
        self.shutdown_event = shutdown_event
        self.host = host
        self.port = port
        self.server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        log.info(f"✅ Control server listening on {self.host}:{self.port}")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        log.info(f"Control client connected from {addr}")
        
        def reply(msg: str):
            writer.write((msg + "\n").encode('utf-8'))

        reply(self.HELP_TEXT)
        await writer.drain()
        
        while not self.shutdown_event.is_set():
            writer.write(b"CM4000> ")
            await writer.drain()
            
            try:
                line = await reader.readline()
                if not line:
                    break
                cmd = line.decode('utf-8').strip().lower()
                if not cmd:
                    continue
                parts = cmd.split()
                action = parts[0]
                
                if action in ('quit', 'exit'):
                    reply("  Closing connection...")
                    break
                elif action == 'shutdown':
                    reply("⏻  Shutting down simulator...")
                    self.shutdown_event.set()
                    break
                elif action == 'help':
                    reply(self.HELP_TEXT)
                elif action == 'status':
                    reply(self._cmd_status())
                elif action == 'snapshot':
                    reply(self._cmd_snapshot())
                elif action in ('sag', 'swell', 'overload', 'harmonic', 'phase_loss'):
                    reply(self._cmd_event(action, parts[1:]))
                elif action == 'outage':
                    reply(self._cmd_outage(parts[1:]))
                elif action == 'low_pf':
                    reply(self._cmd_low_pf(parts[1:]))
                else:
                    reply(f"  ❌ Unknown command: {action}. Type 'help'.")
                
                await writer.drain()
                
            except ConnectionResetError:
                break
            except Exception as e:
                log.error(f"Error handling control client {addr}: {e}")
                break

        log.info(f"Control client disconnected from {addr}")
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    def _cmd_event(self, action: str, args: list) -> str:
        if len(args) < 3 and action != 'phase_loss':
            if not (action == 'phase_loss' and len(args) >= 2):
                return f"  ❌ Usage: {action} <phase|all> <value> <duration_s>"
                
        phase = args[0]
        if phase not in ('a', 'b', 'c', 'all'):
            return "  ❌ Phase must be: a, b, c, or all"

        try:
            if action == 'phase_loss':
                duration = float(args[1])
                value = 0.0
            else:
                value = float(args[1])
                duration = float(args[2])
        except ValueError:
            return "  ❌ Value and duration must be numbers"

        if action == 'sag':
            mag = 1.0 - (value / 100.0)
            event = PowerEvent('sag', phase, mag, duration)
            label = f"Voltage SAG -{value}%"
        elif action == 'swell':
            mag = 1.0 + (value / 100.0)
            event = PowerEvent('swell', phase, mag, duration)
            label = f"Voltage SWELL +{value}%"
        elif action == 'overload':
            event = PowerEvent('overload', phase, value, duration)
            label = f"Current OVERLOAD x{value}"
        elif action == 'harmonic':
            event = PowerEvent('harmonic_spike', phase, value, duration)
            label = f"Harmonic SPIKE +{value}% THD"
        elif action == 'phase_loss':
            event = PowerEvent('phase_loss', phase, 0.0, duration)
            label = f"PHASE LOSS"
        else:
            return ""

        self.engine.inject_event(event)
        return f"  ⚡ Injected: {label} on phase {phase.upper()} for {duration}s"

    def _cmd_outage(self, args: list) -> str:
        if len(args) < 1:
            return "  ❌ Usage: outage <duration_s>"
        try:
            duration = float(args[0])
            event = PowerEvent('outage', 'all', 0.0, duration)
            self.engine.inject_event(event)
            return f"  ⚡ Injected: FULL OUTAGE for {duration}s"
        except ValueError:
            return "  ❌ Duration must be a number"

    def _cmd_low_pf(self, args: list) -> str:
        if len(args) < 2:
            return "  ❌ Usage: low_pf <pf_value> <duration_s>"
        try:
            value = float(args[0])
            duration = float(args[1])
            event = PowerEvent('low_pf', 'all', value, duration)
            self.engine.inject_event(event)
            return f"  ⚡ Injected: LOW PF ({value}) for {duration}s"
        except ValueError:
            return "  ❌ Value and duration must be numbers"

    def _cmd_status(self) -> str:
        events = self.engine.active_events
        if not events:
            return "  ✅ No active events"
        lines = [f"  📊 Active events ({len(events)}):"]
        for e in events:
            lines.append(f"     • {e.event_type.upper()} phase={e.phase.upper()} "
                         f"mag={e.magnitude:.2f} remaining={e.remaining_s:.1f}s")
        return "\n".join(lines)

    def _cmd_snapshot(self) -> str:
        snap = self.engine.snapshot()
        return (
            "\n  ╔══════════════════════════════════════════╗\n"
            "  ║         Current Measurements             ║\n"
            "  ╠══════════════════════════════════════════╣\n"
            f"  ║  Vln:  {snap['Vln_a']:>7.1f} │ {snap['Vln_b']:>7.1f} │ {snap['Vln_c']:>7.1f} V   ║\n"
            f"  ║  Vll:  {snap['Vll_ab']:>7.1f} │ {snap['Vll_bc']:>7.1f} │ {snap['Vll_ca']:>7.1f} V   ║\n"
            f"  ║  I:    {snap['I_a']:>7.1f} │ {snap['I_b']:>7.1f} │ {snap['I_c']:>7.1f} A   ║\n"
            f"  ║  kW:   {snap['kW_a']:>7.1f} │ {snap['kW_b']:>7.1f} │ {snap['kW_c']:>7.1f} kW  ║\n"
            f"  ║  PF:   {snap['PF_a']:>7.3f} │ {snap['PF_b']:>7.3f} │ {snap['PF_c']:>7.3f}     ║\n"
            f"  ║  Freq: {snap['Freq']:>7.2f} Hz                        ║\n"
            f"  ║  THDv: {snap['THD_V_a']:>5.1f}% │ {snap['THD_V_b']:>5.1f}% │ {snap['THD_V_c']:>5.1f}%       ║\n"
            f"  ║  THDi: {snap['THD_I_a']:>5.1f}% │ {snap['THD_I_b']:>5.1f}% │ {snap['THD_I_c']:>5.1f}%       ║\n"
            f"  ║  kWh:  {snap['kWh_del']:>10.1f} delivered             ║\n"
            f"  ║  kVARh:{snap['kVARh_del']:>10.1f} delivered             ║\n"
            "  ╚══════════════════════════════════════════╝\n"
        )


# ─────────────────────────────────────────────────────────────
# Main Server
# ─────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="CM4000 Modbus-TCP Simulator — Schneider Electric PowerLogic"
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5020,
                        help="TCP port (default: 5020, use 502 for standard)")
    parser.add_argument("--control-port", type=int, default=5021,
                        help="TCP port for remote control CLI (default: 5021)")
    parser.add_argument("--unit-id", type=int, default=1,
                        help="Modbus Unit ID / Device ID (default: 1)")
    parser.add_argument("--update-rate", type=float, default=1.0,
                        help="Data update interval in seconds (default: 1.0)")
    parser.add_argument("--v-nominal", type=float, default=7620.0,
                        help="Nominal Vln voltage (default: 7620V for 13.2kV MT)")
    parser.add_argument("--current", type=float, default=100.0,
                        help="Nominal phase current (default: 100A)")
    parser.add_argument("--freq", type=float, default=50.0,
                        help="Nominal frequency (default: 50Hz)")
    parser.add_argument("--pf", type=float, default=0.92,
                        help="Nominal power factor (default: 0.92)")
    return parser.parse_args()


async def run_server(args):
    """Initialize and run the Modbus TCP server with dynamic data updates."""

    # ── Profile ──
    profile = BaselineProfile(
        v_ln=args.v_nominal,
        v_ll=args.v_nominal * 1.732,
        current=args.current,
        freq=args.freq,
        pf=args.pf,
    )

    # ── Data Engine ──
    engine = DataEngine(profile)

    # ── SimDevice (pymodbus 3.13 native API) ──
    block_size = MAX_REGISTER + 100
    sim_data = [
        SimData(
            address=1,
            count=block_size,
            values=0,
            datatype=DataType.REGISTERS,
        )
    ]
    device = SimDevice(
        id=args.unit_id,
        simdata=sim_data,
        action=_register_action,
    )

    # ── Shutdown Coordination ──
    shutdown_event = threading.Event()

    # ── Banner ──
    print(BANNER.format(
        reg_count=len(REGISTER_MAP),
        host=args.host, port=args.port,
        c_port=args.control_port,
        unit_id=args.unit_id,
        rate=args.update_rate,
    ))

    # ── Register Updater Thread ──
    updater = RegisterUpdater(engine, args.update_rate)
    updater.start()
    log.info("✅ Register updater started")

    # ── Control Server (TCP) ──
    control_server = ControlServer(engine, shutdown_event, args.host, args.control_port)
    await control_server.start()

    # ── Start Modbus TCP Server ──
    log.info(f"🔌 Starting Modbus-TCP server on {args.host}:{args.port}")

    try:
        server = ModbusTcpServer(device, address=(args.host, args.port))
        serve_task = asyncio.create_task(server.serve_forever())

        # Poll shutdown event
        while not shutdown_event.is_set():
            await asyncio.sleep(0.5)

        await server.shutdown()
        log.info("Server stopped.")
    except OSError as e:
        if e.errno == 98:
            log.error(f"❌ Port {args.port} or {args.control_port} already in use.")
            sys.exit(1)
        raise
    finally:
        await control_server.stop()
        updater.stop()


def main():
    args = parse_args()
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        log.info("\n⏻  Simulator stopped by user (Ctrl+C)")
        sys.exit(0)


if __name__ == "__main__":
    main()
