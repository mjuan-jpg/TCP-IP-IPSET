#!/usr/bin/env python3
"""
CM4000 Dynamic Data Engine
Generates realistic, fluctuating electrical values with statistical noise
and supports event injection (sags, swells, alarms).
"""

import math
import time
import random
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict

# ─────────────────────────────────────────────────────────────
# Baseline Electrical Profile (380V / 50Hz industrial network)
# ─────────────────────────────────────────────────────────────

@dataclass
class BaselineProfile:
    """Nominal electrical parameters for a 3-phase industrial network (13.2 kV MT)."""
    v_ln: float = 7621.02     # Phase-Neutral voltage (V) -> 13200 / sqrt(3)
    v_ll: float = 13200.0     # Phase-Phase voltage (V)
    current: float = 100.0    # Phase current (A)
    pf: float = 0.92          # Power factor (lagging)
    freq: float = 50.0        # Frequency (Hz)
    thd_v: float = 2.5        # THD voltage (%)
    thd_i: float = 8.0        # THD current (%)
    kwh_initial: float = 125000.0   # Initial energy (kWh)
    kvarh_initial: float = 45000.0  # Initial reactive energy


# ─────────────────────────────────────────────────────────────
# Event Types for Injection
# ─────────────────────────────────────────────────────────────

@dataclass
class PowerEvent:
    """Represents an injected power quality event."""
    event_type: str       # 'sag', 'swell', 'overload', 'harmonic_spike'
    phase: str            # 'a', 'b', 'c', or 'all'
    magnitude: float      # Multiplier (e.g., 0.7 for 30% sag, 1.15 for 15% swell)
    duration_s: float     # Duration in seconds
    start_time: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return (time.time() - self.start_time) < self.duration_s

    @property
    def remaining_s(self) -> float:
        return max(0, self.duration_s - (time.time() - self.start_time))


class DataEngine:
    """
    Generates realistic electrical measurement data with:
    - Gaussian noise for natural fluctuation
    - Phase angle offsets (120° separation)
    - Slow sinusoidal drift (load cycling)
    - Event injection support
    """

    def __init__(self, profile: Optional[BaselineProfile] = None):
        self.profile = profile or BaselineProfile()
        self._lock = threading.Lock()
        self._events: list[PowerEvent] = []
        self._start_time = time.time()

        # Energy accumulators
        self._kwh_del = self.profile.kwh_initial
        self._kwh_rec = 0.0
        self._kvarh_del = self.profile.kvarh_initial
        self._kvarh_rec = 0.0
        self._kvah_del = self.profile.kwh_initial * 1.08
        self._last_energy_update = time.time()

        # Peak demands
        self._peak_kw = 0.0
        self._peak_kvar = 0.0
        self._peak_kva = 0.0

    # ── Event Injection ──

    def inject_event(self, event: PowerEvent):
        """Add a power quality event to the simulation."""
        with self._lock:
            self._events.append(event)

    def _get_phase_event_multiplier(self, phase: str) -> float:
        """Get combined multiplier from all active events for a phase."""
        mult = 1.0
        with self._lock:
            self._events = [e for e in self._events if e.is_active]
            for e in self._events:
                if e.phase == phase or e.phase == 'all':
                    if e.event_type in ('sag', 'swell'):
                        mult *= e.magnitude
                    elif e.event_type == 'outage':
                        mult *= 0.005  # Drops voltage/current to 0.5%
                    elif e.event_type == 'phase_loss':
                        mult *= 0.0  # Total loss
        return mult

    def _get_harmonic_event_boost(self, phase: str) -> float:
        """Get additive THD boost from harmonic spike events."""
        boost = 0.0
        with self._lock:
            for e in self._events:
                if e.is_active and e.event_type == 'harmonic_spike':
                    if e.phase == phase or e.phase == 'all':
                        boost += e.magnitude
        return boost

    # ── Noise & Drift Generators ──

    @staticmethod
    def _gaussian(mean: float, std_pct: float) -> float:
        """Generate a value with Gaussian noise (std_pct = % of mean)."""
        return random.gauss(mean, mean * std_pct / 100.0)

    def _load_drift(self) -> float:
        """Slow sinusoidal drift simulating load cycling (±5% over ~120s)."""
        elapsed = time.time() - self._start_time
        return 1.0 + 0.05 * math.sin(2 * math.pi * elapsed / 120.0)

    def _phase_offset(self, phase: str) -> float:
        """Small static offset per phase to simulate imbalance (±1–2%)."""
        offsets = {'a': 1.005, 'b': 0.998, 'c': 1.002}
        return offsets.get(phase, 1.0)

    # ── Measurement Generators ──

    def get_voltage_ln(self, phase: str) -> float:
        base = self.profile.v_ln * self._phase_offset(phase) * self._load_drift()
        base *= self._get_phase_event_multiplier(phase)
        return self._gaussian(base, 0.3)

    def get_voltage_ll(self, phase_pair: str) -> float:
        base = self.profile.v_ll * self._load_drift()
        # Derive from phase voltages for realism
        if phase_pair == 'ab':
            v = (self.get_voltage_ln('a') + self.get_voltage_ln('b')) / 2 * math.sqrt(3)
        elif phase_pair == 'bc':
            v = (self.get_voltage_ln('b') + self.get_voltage_ln('c')) / 2 * math.sqrt(3)
        else:
            v = (self.get_voltage_ln('c') + self.get_voltage_ln('a')) / 2 * math.sqrt(3)
        return v

    def get_current(self, phase: str) -> float:
        base = self.profile.current * self._phase_offset(phase) * self._load_drift()
        event_mult = self._get_phase_event_multiplier(phase)
        # Overload events
        with self._lock:
            for e in self._events:
                if e.is_active and e.event_type == 'overload':
                    if e.phase == phase or e.phase == 'all':
                        base *= e.magnitude
        base *= event_mult
        return max(0, self._gaussian(base, 1.5))

    def get_power_factor(self, phase: str) -> float:
        pf = self.profile.pf
        with self._lock:
            for e in self._events:
                if e.is_active and e.event_type == 'low_pf':
                    if e.phase == phase or e.phase == 'all':
                        pf = e.magnitude
        return max(0.0, min(1.0, self._gaussian(pf, 0.8)))

    def get_frequency(self) -> float:
        # Frecuencia estricta entre 49.9 y 50.1 Hz
        val = self._gaussian(self.profile.freq, 0.05)
        return max(49.9, min(50.1, val))

    def get_thd_v(self, phase: str) -> float:
        base = self.profile.thd_v + self._get_harmonic_event_boost(phase)
        # Restricción normativa: THD_v NUNCA debe superar el 5.0% en estado estacionario
        return max(0.0, min(5.0, self._gaussian(base, 5.0)))

    def get_thd_i(self, phase: str) -> float:
        base = self.profile.thd_i + self._get_harmonic_event_boost(phase)
        # Restricción: THD_i entre 5% y 20%
        return max(5.0, min(20.0, self._gaussian(base, 8.0)))

    def get_harmonic_v(self, phase: str, order: int) -> float:
        """Individual voltage harmonic magnitude (% of fundamental). Priorities: 5, 7, 11, 13"""
        if order not in [5, 7, 11, 13]: return 0.0
        base_pct = (100.0 / (order ** 1.8)) * (self.profile.thd_v / 5.0)
        base_pct += self._get_harmonic_event_boost(phase) * (0.5 / order)
        return max(0, self._gaussian(base_pct, 10.0))

    def get_harmonic_i(self, phase: str, order: int) -> float:
        """Individual current harmonic magnitude (% of fundamental)."""
        if order not in [5, 7, 11, 13]: return 0.0
        base_pct = (100.0 / (order ** 1.5)) * (self.profile.thd_i / 8.0)
        base_pct += self._get_harmonic_event_boost(phase) * (1.0 / order)
        return max(0, self._gaussian(base_pct, 12.0))

    # ── Energy Accumulators ──

    def _update_energy(self, kw_total: float, kvar_total: float, kva_total: float):
        """Update energy counters based on power and elapsed time."""
        now = time.time()
        dt_h = (now - self._last_energy_update) / 3600.0
        self._last_energy_update = now

        if kw_total >= 0:
            self._kwh_del += kw_total * dt_h
        else:
            self._kwh_rec += abs(kw_total) * dt_h

        if kvar_total >= 0:
            self._kvarh_del += kvar_total * dt_h
        else:
            self._kvarh_rec += abs(kvar_total) * dt_h

        self._kvah_del += abs(kva_total) * dt_h

        # Update peak demands
        self._peak_kw = max(self._peak_kw, abs(kw_total))
        self._peak_kvar = max(self._peak_kvar, abs(kvar_total))
        self._peak_kva = max(self._peak_kva, abs(kva_total))

    # ── Full Snapshot ──

    def snapshot(self) -> Dict[str, float]:
        """Generate a complete snapshot enforcing strict MT physical relationships."""
        data = {}
        phases = ['a', 'b', 'c']

        # Voltages L-N
        for p in phases:
            v_ln = self.get_voltage_ln(p)
            # Acotar voltaje en estado estable (-5% a +5%)
            if not self.active_events:
                v_ln = max(self.profile.v_ln * 0.95, min(self.profile.v_ln * 1.05, v_ln))
            data[f'Vln_{p}'] = v_ln
        data['Vln_avg'] = sum(data[f'Vln_{p}'] for p in phases) / 3.0

        # Voltages L-L (Relación ideal estricta: VL = √3 * VF)
        data['Vll_ab'] = data['Vln_a'] * math.sqrt(3)
        data['Vll_bc'] = data['Vln_b'] * math.sqrt(3)
        data['Vll_ca'] = data['Vln_c'] * math.sqrt(3)
        data['Vll_avg'] = sum(data[k] for k in ['Vll_ab', 'Vll_bc', 'Vll_ca']) / 3.0

        # Currents
        for p in phases:
            data[f'I_{p}'] = self.get_current(p)
        # Restricción estricta MT Delta: I_n = 0.0A
        data['I_n'] = 0.0
        data['I_avg'] = sum(data[f'I_{p}'] for p in phases) / 3.0

        # Power Factor (Rango estricto 0.85 a 1.00 en estado estable)
        for p in phases:
            pf = self.get_power_factor(p)
            if not self.active_events:
                pf = max(0.85, min(1.00, pf))
            data[f'PF_{p}'] = pf
        data['PF_tot'] = sum(data[f'PF_{p}'] for p in phases) / 3.0

        # Potencia Total Trifásica (S = √3 * VL_avg * IL_avg)
        data['kVA_tot'] = (math.sqrt(3) * data['Vll_avg'] * data['I_avg']) / 1000.0
        data['kW_tot'] = data['kVA_tot'] * data['PF_tot']
        # Triángulo cerrado: S = sqrt(P^2 + Q^2) -> Q = sqrt(S^2 - P^2)
        data['kVAR_tot'] = math.sqrt(abs(data['kVA_tot']**2 - data['kW_tot']**2))

        # Potencia por fase (Distribuida perfectamente para no romper las sumas)
        for p in phases:
            data[f'kVA_{p}'] = data['kVA_tot'] / 3.0
            data[f'kW_{p}'] = data['kW_tot'] / 3.0
            data[f'kVAR_{p}'] = data['kVAR_tot'] / 3.0

        # Frequency
        data['Freq'] = self.get_frequency()

        # THD
        for p in phases:
            data[f'THD_V_{p}'] = self.get_thd_v(p)
            data[f'THD_I_{p}'] = self.get_thd_i(p)
        data['THD_I_n'] = 0.0  # Assumed 0 for simulation

        # Individual harmonics (3rd–15th)
        for p in phases:
            for h in range(3, 16):
                data[f'V_H{h}_{p}'] = self.get_harmonic_v(p, h)
                data[f'I_H{h}_{p}'] = self.get_harmonic_i(p, h)

        # Energy update
        self._update_energy(data['kW_tot'], data['kVAR_tot'], data['kVA_tot'])
        data['kWh_del'] = self._kwh_del
        data['kWh_rec'] = self._kwh_rec
        data['kVARh_del'] = self._kvarh_del
        data['kVARh_rec'] = self._kvarh_rec
        data['kVAh_del'] = self._kvah_del
        data['kWh_tot'] = self._kwh_del + self._kwh_rec
        
        # Peaks
        data['Peak_kW_tot'] = self._peak_kw
        data['Peak_kVAR_tot'] = self._peak_kvar
        data['Peak_kVA_tot'] = self._peak_kva

        return data

    @property
    def active_events(self) -> list[PowerEvent]:
        with self._lock:
            return [e for e in self._events if e.is_active]
