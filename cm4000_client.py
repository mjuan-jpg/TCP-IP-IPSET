#!/usr/bin/env python3
"""
CM4000 Test Client — Reads registers from the simulator and displays them.
Usage: python cm4000_client.py [--host localhost] [--port 5020] [--unit-id 1]
"""

import struct
import argparse
import time
import sys
import os

from pymodbus.client import ModbusTcpClient
from cm4000_registers import REGISTER_MAP, REG_BY_NAME, int16_to_float, int16_to_pf


def read_value(client, reg, unit: int) -> float:
    """Read a register according to its format."""
    if reg.fmt == 'mod10k':
        result = client.read_holding_registers(reg.address, count=4, device_id=unit)
        if result.isError(): return float('nan')
        r = result.registers
        return r[0] + r[1] * 10000 + r[2] * 10000**2 + r[3] * 10000**3
    else:
        result = client.read_holding_registers(reg.address, count=1, device_id=unit)
        if result.isError(): return float('nan')
        val = result.registers[0]
        if reg.fmt == 'int16_pf':
            return int16_to_pf(val)
        else:
            return int16_to_float(val, reg.scale, signed=(reg.fmt == 'int16'))


def main():
    parser = argparse.ArgumentParser(description="CM4000 Modbus Test Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=5020, help="Server port")
    parser.add_argument("--unit-id", type=int, default=1, help="Modbus Unit ID")
    parser.add_argument("--loop", action="store_true", help="Continuous polling")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval (s)")
    args = parser.parse_args()

    client = ModbusTcpClient(args.host, port=args.port)
    if not client.connect():
        print(f"❌ Cannot connect to {args.host}:{args.port}")
        sys.exit(1)

    print(f"✅ Connected to CM4000 simulator at {args.host}:{args.port}\n")

    try:
        while True:
            # Limpiar la pantalla para crear un efecto de "dashboard" en vivo
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()
            
            print("╔════════════════════════════════════════════════════════════╗")
            print("║          CM4000 Register Readings                         ║")
            print("╠════════════════════════════════════════════════════════════╣")

            # Key parameters to read
            key_regs = [
                "Vln_a", "Vln_b", "Vln_c",
                "Vll_ab", "Vll_bc", "Vll_ca",
                "I_a", "I_b", "I_c", "I_n", "I_avg",
                "kW_a", "kW_b", "kW_c", "kW_tot",
                "kVAR_tot", "kVA_tot",
                "PF_a", "PF_b", "PF_c", "PF_tot",
                "Freq",
                "THD_V_a", "THD_V_b", "THD_V_c",
                "THD_I_a", "THD_I_b", "THD_I_c",
            ]

            for name in key_regs:
                reg = REG_BY_NAME.get(name)
                if not reg:
                    continue
                if reg.fmt in ('uint16', 'int16', 'int16_pf', 'mod10k'):
                    val = read_value(client, reg, args.unit_id)
                else:
                    continue

                unit_str = f" {reg.unit}" if reg.unit else ""
                print(f"║  {name:<15} [Reg {reg.address:>5}] = {val:>12.3f}{unit_str:<6} ║")

            # Peak Demands
            print("║──────────────── Peak Demand ───────────────────────────────║")
            for name in ["Peak_kW_tot", "Peak_kVAR_tot", "Peak_kVA_tot"]:
                reg = REG_BY_NAME.get(name)
                if reg:
                    val = read_value(client, reg, args.unit_id)
                    print(f"║  {name:<15} [Reg {reg.address:>5}] = {val:>12.3f} {reg.unit:<6} ║")

            # Energy (Mod-10000)
            print("║──────────────── Energy ────────────────────────────────────║")
            for name in ["kWh_del", "kWh_rec", "kVARh_del", "kVARh_rec", "kWh_tot"]:
                reg = REG_BY_NAME.get(name)
                if reg:
                    val = read_value(client, reg, args.unit_id)
                    print(f"║  {name:<15} [Reg {reg.address:>5}] = {val:>12.0f} {reg.unit:<6} ║")

            print("╚════════════════════════════════════════════════════════════╝")
            print(f"  Last poll: {time.strftime('%H:%M:%S')}\n")

            if not args.loop:
                break
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n⏻  Client stopped.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
