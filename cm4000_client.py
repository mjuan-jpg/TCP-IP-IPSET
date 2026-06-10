#!/usr/bin/env python3
"""
CM4000 Data Acquisition Node (Telegraf Replacement)
---------------------------------------------------
Este script reemplaza la funcionalidad de Telegraf, implementando:
1. Polling Modbus-TCP cada 1 segundo.
2. Buffers en memoria y promedios matemáticos cada 15 minutos.
3. Inserción masiva en InfluxDB.
4. Motor de evaluación de alarmas en tiempo real con histéresis pura.
5. Notificaciones asíncronas fire-and-forget vía cm4000_notifier.
"""

import time
import logging
import os
import math
from datetime import datetime, timezone
from typing import Dict, List

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from cm4000_registers import REGISTER_MAP, REG_BY_NAME, int16_to_float, int16_to_pf
from cm4000_notifier import dispatch_alert_async

# ─────────────────────────────────────────────────────────────
# Configuración desde entorno
# ─────────────────────────────────────────────────────────────

MODBUS_HOST       = os.environ.get("MODBUS_HOST", "simulator")
MODBUS_PORT       = int(os.environ.get("MODBUS_PORT", 5020))
MODBUS_UNIT_ID    = 1
POLL_INTERVAL_SEC = 1.0

INFLUX_URL    = os.environ.get("INFLUX_URL",    "http://influxdb:8086")
INFLUX_TOKEN  = os.environ.get("INFLUX_TOKEN",  "my-super-secret-auth-token")
INFLUX_ORG    = os.environ.get("INFLUX_ORG",    "ipset")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "cm4000_data")

AVERAGE_WINDOW_SEC = 90   # ventana de promediado (~1 min 30 s)

# ─────────────────────────────────────────────────────────────
# Límites normativos MT 13.2 kV / 50 Hz (fijos, no configurables)
# ─────────────────────────────────────────────────────────────

VLL_NOM    = 13_200.0          # V — tensión nominal L-L
VLN_NOM    =  7_621.0          # V — tensión nominal L-N (= VLL/√3)

VLL_SAG    = VLL_NOM * 0.90    # 11 880 V
VLL_SWELL  = VLL_NOM * 1.10    # 14 520 V

VLN_LOW    = VLN_NOM * 0.93    #  7 087.53 V  (−7 %)
VLN_HIGH   = VLN_NOM * 1.07    #  8 154.47 V  (+7 %)

I_N_MAX    = 0.1               # A — máximo neutro permitido en delta MT
I_OC       = 120.0             # A — umbral de sobrecorriente por fase (operativo)
PF_MIN     = 0.85              # mínimo factor de potencia
THD_V_MAX  = 5.0               # % — límite EN 50160

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("CM4000-DAQ")


# ─────────────────────────────────────────────────────────────
# Helpers de formato
# ─────────────────────────────────────────────────────────────

def _alarm_subject(alarm_type: str, status: str) -> str:
    """Construye el asunto de la notificación según el estado."""
    if status == "ACTIVA":
        return f"🚨 ALARMA ACTIVA: {alarm_type}"
    return f"✅ ALARMA NORMALIZADA: {alarm_type}"


def _alarm_body(alarm_type: str, status: str, details: str) -> str:
    """Construye el cuerpo detallado del mensaje de notificación."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    emoji = "🔴" if status == "ACTIVA" else "🟢"
    return (
        f"Estado:    {emoji} {status}\n"
        f"Alarma:    {alarm_type}\n"
        f"Detalle:   {details}\n"
        f"Timestamp: {ts}\n"
        f"Equipo:    Schneider CM4000 — Red MT 13.2 kV / 50 Hz"
    )


# ─────────────────────────────────────────────────────────────
# Adquisidor principal
# ─────────────────────────────────────────────────────────────

class CM4000Adquisidor:

    def __init__(self):
        # Clientes de comunicación
        self.modbus   = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
        self.influx   = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self.write_api = self.influx.write_api(write_options=SYNCHRONOUS)

        # Buckets
        self.bucket_historic = INFLUX_BUCKET
        self.bucket_realtime = os.environ.get("INFLUX_BUCKET_REALTIME", "cm4000_realtime")

        # Buffers de datos para promedios de ventana
        self.buffers: Dict[str, List[float]] = {r.name: [] for r in REGISTER_MAP}
        self.last_energy_values: Dict[str, float] = {}
        self.peak_demand_kw: float = 0.0
        # Ventanas completadas: la alarma Demanda_Superada solo se arma
        # a partir de la 2ª ventana para evitar falsos disparos al arranque.
        self._windows_completed: int = 0

        # Máquina de estados de alarmas — Histéresis Pura
        # False = normal, True = alarma activa
        self.alarms_state: Dict[str, bool] = {
            "Tension_Sag_Swell":        False,
            "Tension_Fase_Anomala":     False,
            "Corriente_Neutro_Anomala": False,
            "Sobrecorriente":           False,
            "FP_Bajo":                  False,
            "THD_Elevado":              False,
            "Demanda_Superada":         False,
            "Falla_Comunicacion":       False,
        }

    # ── Modbus ────────────────────────────────────────────────

    def _read_register(self, reg_name: str) -> float:
        """Lee un registro individual y lo decodifica según su formato."""
        reg = REG_BY_NAME.get(reg_name)
        if not reg:
            return float("nan")

        if reg.fmt == "mod10k":
            result = self.modbus.read_holding_registers(
                reg.address, count=4, device_id=MODBUS_UNIT_ID
            )
            if result.isError():
                raise ModbusException("Error leyendo Mod10k")
            r = result.registers
            return r[0] + r[1] * 10_000 + r[2] * 10_000**2 + r[3] * 10_000**3
        else:
            result = self.modbus.read_holding_registers(
                reg.address, count=1, device_id=MODBUS_UNIT_ID
            )
            if result.isError():
                raise ModbusException("Error leyendo int16")
            val = result.registers[0]
            if reg.fmt == "int16_pf":
                return int16_to_pf(val)
            return int16_to_float(val, reg.scale, signed=(reg.fmt == "int16"))

    # ── Conexión ──────────────────────────────────────────────

    def connect(self) -> bool:
        if not self.modbus.connect():
            log.error("❌ No se pudo conectar al Simulador Modbus")
            return False
        try:
            health = self.influx.health()
            if health.status != "pass":
                log.error("❌ No se pudo conectar a InfluxDB")
                return False
            # Cargar el pico histórico de demanda desde InfluxDB
            self._load_historical_peak()
        except Exception as exc:
            log.error(f"❌ Excepción conectando a InfluxDB: {exc}")
            return False
        log.info("✅ Conectado a Modbus-TCP y InfluxDB.")
        return True

    def _load_historical_peak(self) -> None:
        """Consulta InfluxDB para obtener el último pico histórico registrado."""
        try:
            query_api = self.influx.query_api()
            query = f'''
            from(bucket: "{self.bucket_historic}")
              |> range(start: 0)
              |> filter(fn: (r) => r["_measurement"] == "mediciones_electricas")
              |> filter(fn: (r) => r["_field"] == "Peak_kW_tot")
              |> keep(columns: ["_value"])
              |> last()
            '''
            result = query_api.query(query)
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None and val > 0:
                        self.peak_demand_kw = float(val)
                        log.info(f"💾 Pico de demanda histórico cargado desde InfluxDB: {self.peak_demand_kw:.2f} kW")
                        return
            log.info("ℹ️ No se encontró un pico de demanda previo en InfluxDB. Se iniciará desde 0.0 kW.")
        except Exception as exc:
            log.warning(f"⚠️ No se pudo recuperar el pico histórico desde InfluxDB: {exc}. Se iniciará desde 0.0 kW.")

    # ── Motor de Alarmas — Histéresis Pura ────────────────────

    def process_alarms(self, data: Dict[str, float]) -> None:
        """
        Evalúa las 7 reglas normativas de alarma para red MT 13.2 kV / 50 Hz.
        Solo actúa en transición de estado (flanco de subida / bajada).
        """

        # ── 1. Tensión Sag / Swell (L-L promedio) ─────────────
        vll_avg = data.get("Vll_avg", VLL_NOM)
        self._trigger_alarm_state(
            alarm_type="Tension_Sag_Swell",
            is_active=(vll_avg < VLL_SAG or vll_avg > VLL_SWELL),
            value=vll_avg,
            details=f"Vll_avg = {vll_avg:.2f} V  (límites: {VLL_SAG:.0f}–{VLL_SWELL:.0f} V)",
        )

        # ── 2. Tensión de Fase Anómala (L-N ± 7 %) ────────────
        vln_a = data.get("Vln_a", VLN_NOM)
        vln_b = data.get("Vln_b", VLN_NOM)
        vln_c = data.get("Vln_c", VLN_NOM)
        phase_bad = any(v < VLN_LOW or v > VLN_HIGH for v in (vln_a, vln_b, vln_c))
        self._trigger_alarm_state(
            alarm_type="Tension_Fase_Anomala",
            is_active=phase_bad,
            value=vln_a,
            details=(
                f"Vln A={vln_a:.0f} V, B={vln_b:.0f} V, C={vln_c:.0f} V"
                f"  (límites: {VLN_LOW:.0f}–{VLN_HIGH:.0f} V)"
            ),
        )

        # ── 3. Corriente de Neutro Anómala (MT Delta, debe ser 0) ──
        i_n = data.get("I_n", 0.0)
        self._trigger_alarm_state(
            alarm_type="Corriente_Neutro_Anomala",
            is_active=(i_n > I_N_MAX),
            value=i_n,
            details=f"I_n = {i_n:.3f} A  (máx permitido: {I_N_MAX} A)",
        )

        # ── 4. Sobrecorriente por fase (cualquier fase > I_OC) ─
        i_a = data.get("I_a", 0.0)
        i_b = data.get("I_b", 0.0)
        i_c = data.get("I_c", 0.0)
        oc_phases = [
            f"L{ph}={val:.1f} A"
            for ph, val in (("1", i_a), ("2", i_b), ("3", i_c))
            if val > I_OC
        ]
        self._trigger_alarm_state(
            alarm_type="Sobrecorriente",
            is_active=bool(oc_phases),
            value=max(i_a, i_b, i_c),
            details=(
                f"Fases en sobrecorriente: {', '.join(oc_phases)}"
                f"  (umbral: {I_OC:.0f} A)"
                if oc_phases
                else f"Corrientes normalizadas: L1={i_a:.1f} A, L2={i_b:.1f} A, L3={i_c:.1f} A"
            ),
        )

        # ── 5. Factor de Potencia Bajo ─────────────────────────
        pf_tot = data.get("PF_tot", 1.0)
        self._trigger_alarm_state(
            alarm_type="FP_Bajo",
            is_active=(0.0 < pf_tot < PF_MIN),
            value=pf_tot,
            details=f"PF_tot = {pf_tot:.3f}  (mínimo: {PF_MIN})",
        )

        # ── 6. THD de Tensión Elevado (fase A, EN 50160) ───────
        thd_va = data.get("THD_V_a", 0.0)
        self._trigger_alarm_state(
            alarm_type="THD_Elevado",
            is_active=(thd_va > THD_V_MAX),
            value=thd_va,
            details=f"THD_V_a = {thd_va:.2f}%  (máx EN 50160: {THD_V_MAX}%)",
        )

        # ── 7. Demanda Máxima Superada ─────────────────────────
        # Solo se arma a partir de la 2ª ventana para evitar falsos disparos
        # al arranque cuando peak_demand_kw se establece por primera vez.
        # Cuando se supera, actualizamos el pico de inmediato para evitar flapeo.
        kw_tot = data.get("kW_tot", 0.0)
        demand_armed = self._windows_completed >= 2 and self.peak_demand_kw > 0
        
        # Durante las ventanas de calentamiento/estabilización, registramos el pico máximo instantáneo observado
        if not demand_armed:
            if kw_tot > self.peak_demand_kw:
                self.peak_demand_kw = kw_tot

        demand_exceeded = demand_armed and kw_tot > self.peak_demand_kw
        if demand_exceeded:
            old_peak = self.peak_demand_kw
            self.peak_demand_kw = kw_tot   # avanzar el pico → impide re-disparo
            log.info(f"📈 Pico actualizado en tiempo real: {old_peak:.2f} → {self.peak_demand_kw:.2f} kW")
        self._trigger_alarm_state(
            alarm_type="Demanda_Superada",
            is_active=demand_exceeded,
            value=kw_tot,
            details=f"kW_tot = {kw_tot:.2f} kW  (nuevo pico: {self.peak_demand_kw:.2f} kW)",
        )

    def _trigger_alarm_state(
        self, alarm_type: str, is_active: bool, value: float, details: str
    ) -> None:
        """
        Histéresis Pura: solo actúa si el estado cambia.

        Flanco de subida (Normal → Alarma):
            - Registra en InfluxDB con estado "ACTIVA"
            - Despacha notificación asíncrona (Telegram + Email en paralelo)

        Flanco de bajada (Alarma → Normal):
            - Registra en InfluxDB con estado "INACTIVA"
            - Despacha notificación asíncrona (Telegram + Email en paralelo)

        Sin cooldown ni re-alertas mientras el estado no cambia.
        """
        was_active = self.alarms_state[alarm_type]

        if is_active and not was_active:
            # ── Flanco de subida ──────────────────────────────
            self.alarms_state[alarm_type] = True
            log.warning(f"🚨 ALARMA ACTIVADA   [{alarm_type}] — {details}")
            self._write_event_to_influx(alarm_type, "ACTIVA", value)
            dispatch_alert_async(
                subject=_alarm_subject(alarm_type, "ACTIVA"),
                body=_alarm_body(alarm_type, "ACTIVA", details),
            )

        elif not is_active and was_active:
            # ── Flanco de bajada ──────────────────────────────
            self.alarms_state[alarm_type] = False
            log.info(f"✅ ALARMA NORMALIZADA [{alarm_type}] — {details}")
            self._write_event_to_influx(alarm_type, "INACTIVA", value)
            dispatch_alert_async(
                subject=_alarm_subject(alarm_type, "INACTIVA"),
                body=_alarm_body(alarm_type, "INACTIVA", details),
            )

    # ── InfluxDB ──────────────────────────────────────────────

    def _write_event_to_influx(self, alarm_type: str, status: str, value: float) -> None:
        """Escribe un evento de alarma en el bucket histórico."""
        point = (
            Point("eventos_alarmas")
            .tag("tipo_alarma", alarm_type)
            .tag("estado", status)
            .field("valor_disparo", float(value))
        )
        try:
            self.write_api.write(bucket=self.bucket_historic, record=point)
        except Exception as exc:
            log.error(f"Error guardando evento en InfluxDB: {exc}")

    def write_15min_averages(self) -> None:
        """Calcula el promedio de los buffers y realiza el bulk write a InfluxDB."""
        self._windows_completed += 1
        log.info(
            f"📊 Calculando promedios (ventana #{self._windows_completed}) y guardando en BD..."
        )

        point = Point("mediciones_electricas")
        avg_kw_tot = 0.0
        avg_v_ab = VLL_NOM
        avg_v_bc = VLL_NOM
        avg_v_ca = VLL_NOM

        for reg in REGISTER_MAP:
            if reg.fmt == "mod10k":
                val = self.last_energy_values.get(reg.name)
                if val is not None:
                    point.field(reg.name, val)
            else:
                data_list = self.buffers[reg.name]
                if data_list:
                    avg_val = sum(data_list) / len(data_list)
                    point.field(reg.name, avg_val)
                    if reg.name == "kW_tot":
                        avg_kw_tot = avg_val
                    elif reg.name == "Vll_ab":
                        avg_v_ab = avg_val
                    elif reg.name == "Vll_bc":
                        avg_v_bc = avg_val
                    elif reg.name == "Vll_ca":
                        avg_v_ca = avg_val
                self.buffers[reg.name].clear()

        point.field("Vll_avg", (avg_v_ab + avg_v_bc + avg_v_ca) / 3.0)

        if avg_kw_tot > self.peak_demand_kw:
            log.info(
                f"📈 Nueva Demanda Máxima: {avg_kw_tot:.2f} kW"
                f"  (anterior: {self.peak_demand_kw:.2f} kW)"
            )
            self.peak_demand_kw = avg_kw_tot
        
        if self.peak_demand_kw > 0:
            point.field("Peak_kW_tot", self.peak_demand_kw)

        try:
            self.write_api.write(bucket=self.bucket_historic, record=point)
            log.info("💾 Bloque de ventana guardado exitosamente en InfluxDB.")
        except Exception as exc:
            log.error(f"Error escribiendo bloque en InfluxDB: {exc}")

    # ── Bucle principal ───────────────────────────────────────

    def run(self) -> None:
        """Bucle principal de adquisición a 1 segundo."""
        if not self.connect():
            return

        samples_count = 0

        try:
            while True:
                start_time = time.time()
                current_data: Dict[str, float] = {}

                try:
                    # ── 1. Lectura Modbus ─────────────────────
                    for reg in REGISTER_MAP:
                        val = self._read_register(reg.name)
                        current_data[reg.name] = val
                        if reg.fmt == "mod10k":
                            self.last_energy_values[reg.name] = val
                        else:
                            self.buffers[reg.name].append(val)

                    # Calcular Vll_avg localmente a partir de las tres tensiones L-L
                    v_ab = current_data.get("Vll_ab", VLL_NOM)
                    v_bc = current_data.get("Vll_bc", VLL_NOM)
                    v_ca = current_data.get("Vll_ca", VLL_NOM)
                    current_data["Vll_avg"] = (v_ab + v_bc + v_ca) / 3.0

                    samples_count += 1

                    # ── 2. Escritura tiempo real (bucket realtime) ──
                    realtime_point = Point("mediciones_realtime")
                    for reg in REGISTER_MAP:
                        if reg.fmt != "mod10k":
                            val = current_data[reg.name]
                            if not math.isnan(val):
                                realtime_point.field(reg.name, val)
                    realtime_point.field("Vll_avg", current_data["Vll_avg"])

                    try:
                        self.write_api.write(bucket=self.bucket_realtime, record=realtime_point)
                    except Exception as exc:
                        log.error(f"❌ Error escribiendo mediciones en tiempo real: {exc}")

                    # Resolución automática de Falla_Comunicacion si volvimos a leer
                    if self.alarms_state["Falla_Comunicacion"]:
                        self._trigger_alarm_state(
                            "Falla_Comunicacion", False, 0.0, "Conexión Modbus restaurada"
                        )

                    # ── 3. Evaluación de alarmas (1 s, histéresis pura) ──
                    self.process_alarms(current_data)

                except ModbusException as exc:
                    # ── Falla_Comunicacion — flanco de subida ──
                    self._trigger_alarm_state(
                        "Falla_Comunicacion", True, 0.0, f"ModbusException: {exc}"
                    )
                    self.modbus.close()
                    self.modbus.connect()

                # ── 4. Promediado de ventana ──────────────────
                if samples_count >= AVERAGE_WINDOW_SEC:
                    self.write_15min_averages()
                    samples_count = 0

                # ── 5. Mantener cadencia estricta a 1.0 s ─────
                elapsed    = time.time() - start_time
                sleep_time = max(0.0, POLL_INTERVAL_SEC - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            log.info("⏻ Deteniendo Adquisidor de Datos CM4000.")
        finally:
            self.modbus.close()
            self.influx.close()


if __name__ == "__main__":
    adquisidor = CM4000Adquisidor()
    adquisidor.run()
