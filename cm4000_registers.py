#!/usr/bin/env python3
"""
CM4000 Register Map — Schneider Electric PowerLogic CM4000
Map updated to match the official Reference Manual (Scale Factors applied).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# ─────────────────────────────────────────────────────────────
# Encoding Utilities
# ─────────────────────────────────────────────────────────────

def float_to_int16(value: float, scale: float, signed: bool = False) -> int:
    """Encode a float to a 16-bit int using a scale factor."""
    val = int(round(value * scale))
    if signed:
        # Convert to 16-bit two's complement
        if val < 0:
            val = (abs(val) ^ 0xFFFF) + 1
        return val & 0xFFFF
    else:
        return max(0, val) & 0xFFFF

def int16_to_float(val: int, scale: float, signed: bool = False) -> float:
    """Decode a 16-bit int to a float using a scale factor."""
    if signed and (val & 0x8000):
        # Decode two's complement
        val = -((val ^ 0xFFFF) + 1)
    return val / scale

def pf_to_int16(value: float) -> int:
    """Encode Power Factor to 16-bit (Bit 15 is sign/lead)."""
    val = int(round(abs(value) * 1000)) & 0x7FFF
    if value < 0:
        val |= 0x8000
    return val

def int16_to_pf(val: int) -> float:
    """Decode Power Factor from 16-bit."""
    is_neg = bool(val & 0x8000)
    mag = val & 0x7FFF
    pf = mag / 1000.0
    return -pf if is_neg else pf

def mod10k_to_registers(value: float) -> Tuple[int, int, int, int]:
    """Encode energy value into 4x16-bit Mod-10000 format."""
    val = int(round(value))
    r1 = val % 10000
    val //= 10000
    r2 = val % 10000
    val //= 10000
    r3 = val % 10000
    r4 = val // 10000
    return r1, r2, r3, r4

# ─────────────────────────────────────────────────────────────
# Register Map Definition
# ─────────────────────────────────────────────────────────────

@dataclass
class RegisterDef:
    address: int
    name: str
    unit: str
    size: int = 1
    fmt: str = 'uint16'  # 'uint16', 'int16', 'int16_pf', 'mod10k'
    scale: float = 1.0


# Addresses based on official manual (with scale factors)
REGISTER_MAP: List[RegisterDef] = [
    # ── Currents (A) ──
    RegisterDef(1100, "I_a", "A", scale=10),
    RegisterDef(1101, "I_b", "A", scale=10),
    RegisterDef(1102, "I_c", "A", scale=10),
    RegisterDef(1103, "I_n", "A", scale=10),
    RegisterDef(1105, "I_avg", "A", scale=10),

    # ── Voltages L-L (V) ──
    RegisterDef(1120, "Vll_ab", "V", scale=1),
    RegisterDef(1121, "Vll_bc", "V", scale=1),
    RegisterDef(1122, "Vll_ca", "V", scale=1),

    # ── Voltages L-N (V) ──
    RegisterDef(1124, "Vln_a", "V", scale=1),
    RegisterDef(1125, "Vln_b", "V", scale=1),
    RegisterDef(1126, "Vln_c", "V", scale=1),
    RegisterDef(1128, "Vln_avg", "V", scale=1),

    # ── Active Power (kW) ──
    RegisterDef(1140, "kW_a", "kW", fmt='int16', scale=1),
    RegisterDef(1141, "kW_b", "kW", fmt='int16', scale=1),
    RegisterDef(1142, "kW_c", "kW", fmt='int16', scale=1),
    RegisterDef(1143, "kW_tot", "kW", fmt='int16', scale=1),

    # ── Reactive Power (kVAR) ──
    RegisterDef(1144, "kVAR_a", "kVAR", fmt='int16', scale=1),
    RegisterDef(1145, "kVAR_b", "kVAR", fmt='int16', scale=1),
    RegisterDef(1146, "kVAR_c", "kVAR", fmt='int16', scale=1),
    RegisterDef(1147, "kVAR_tot", "kVAR", fmt='int16', scale=1),

    # ── Apparent Power (kVA) ──
    RegisterDef(1148, "kVA_a", "kVA", fmt='int16', scale=1),
    RegisterDef(1149, "kVA_b", "kVA", fmt='int16', scale=1),
    RegisterDef(1150, "kVA_c", "kVA", fmt='int16', scale=1),
    RegisterDef(1151, "kVA_tot", "kVA", fmt='int16', scale=1),

    # ── Power Factor (PF) ──
    RegisterDef(1160, "PF_a", "", fmt='int16_pf'),
    RegisterDef(1161, "PF_b", "", fmt='int16_pf'),
    RegisterDef(1162, "PF_c", "", fmt='int16_pf'),
    RegisterDef(1163, "PF_tot", "", fmt='int16_pf'),

    # ── Frequency (Hz) ──
    RegisterDef(1180, "Freq", "Hz", scale=100),

    # ── THD Current (%) ──
    RegisterDef(1190, "THD_I_a", "%", scale=10),
    RegisterDef(1191, "THD_I_b", "%", scale=10),
    RegisterDef(1192, "THD_I_c", "%", scale=10),
    RegisterDef(1193, "THD_I_n", "%", scale=10),

    # ── THD Voltage (%) ──
    RegisterDef(1200, "THD_V_a", "%", scale=10),
    RegisterDef(1201, "THD_V_b", "%", scale=10),
    RegisterDef(1202, "THD_V_c", "%", scale=10),

    # ── Peak Demand ──
    RegisterDef(2154, "Peak_kW_tot", "kW", fmt='int16', scale=1),
    RegisterDef(2169, "Peak_kVAR_tot", "kVAR", fmt='int16', scale=1),
    RegisterDef(2184, "Peak_kVA_tot", "kVA", fmt='int16', scale=1),

    # ── Energy Accumulators (Mod-10000) ──
    RegisterDef(1700, "kWh_rec", "kWh", size=4, fmt='mod10k'),
    RegisterDef(1704, "kVARh_rec", "kVARh", size=4, fmt='mod10k'),
    RegisterDef(1708, "kWh_del", "kWh", size=4, fmt='mod10k'),
    RegisterDef(1712, "kVARh_del", "kVARh", size=4, fmt='mod10k'),
    RegisterDef(1716, "kWh_tot", "kWh", size=4, fmt='mod10k'),
]

REG_BY_ADDR: Dict[int, RegisterDef] = {r.address: r for r in REGISTER_MAP}
REG_BY_NAME: Dict[str, RegisterDef] = {r.name: r for r in REGISTER_MAP}

MAX_REGISTER = max(r.address + r.size for r in REGISTER_MAP)
