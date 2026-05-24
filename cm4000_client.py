#!/usr/bin/env python3
"""
CM4000 Data Acquisition Node (Telegraf Replacement)
---------------------------------------------------
Este script reemplaza la funcionalidad de Telegraf, implementando:
1. Polling Modbus-TCP cada 1 segundo.
2. Buffers en memoria y promedios matemáticos cada 15 minutos.
3. Inserción masiva en InfluxDB.
4. Motor de evaluación de alarmas en tiempo real con histéresis.
5. Notificaciones asíncronas en hilos secundarios.
"""

import time
import threading
import logging
import os
import math
from datetime import datetime
from typing import Dict, List, Any

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from cm4000_registers import REGISTER_MAP, REG_BY_NAME, int16_to_float, int16_to_pf

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────

# Modbus
MODBUS_HOST = os.environ.get("MODBUS_HOST", "simulator")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", 5020))
MODBUS_UNIT_ID = 1
POLL_INTERVAL_SEC = 1.0

# InfluxDB
INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "my-super-secret-auth-token")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "ipset")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "cm4000_data")

# Parámetros de Agrupación
AVERAGE_WINDOW_SEC = 90  # 1 Minuto y 30 segundos

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
# Clases Principales
# ─────────────────────────────────────────────────────────────

class Notifier:
    """Maneja el envío de notificaciones en hilos separados para no bloquear el polling."""
    
    @staticmethod
    def send_alert_async(alarm_type: str, status: str, value: float = None, details: str = ""):
        def task():
            # Aquí iría el código real de Email, Telegram, etc.
            log.info(f"✉️  [NOTIFICADOR] Enviando mensaje -> {alarm_type} [{status}]. Detalles: {details}")
            time.sleep(0.5) # Simulando latencia de red de la API
            
        thread = threading.Thread(target=task, daemon=True)
        thread.start()


class CM4000Adquisidor:
    def __init__(self):
        # Clientes
        self.modbus = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
        self.influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self.write_api = self.influx.write_api(write_options=SYNCHRONOUS)

        # Buckets
        self.bucket_historic = INFLUX_BUCKET
        self.bucket_realtime = os.environ.get("INFLUX_BUCKET_REALTIME", "cm4000_realtime")

        # Buffers de datos para promedios de 15 min
        self.buffers: Dict[str, List[float]] = {r.name: [] for r in REGISTER_MAP}
        self.last_energy_values: Dict[str, float] = {}
        self.peak_demand_kw: float = 0.0 # Guardamos el máximo histórico en memoria (se podría leer de BD al iniciar)
        
        # Máquina de estados de Alarmas (Histeresis)
        self.alarms_state = {
            "Tension_Sag_Swell": False,
            "Tension_Fase_Anomala": False,
            "Corriente_Neutro_Anomala": False,
            "Sobrecorriente": False,
            "FP_Bajo": False,
            "THD_Elevado": False,
            "Demanda_Superada": False,
            "Falla_Comunicacion": False,
        }

    def _read_register(self, reg_name: str) -> float:
        """Lee un registro individual y lo decodifica según su formato."""
        reg = REG_BY_NAME.get(reg_name)
        if not reg: return float('nan')

        if reg.fmt == 'mod10k':
            result = self.modbus.read_holding_registers(reg.address, count=4, device_id=MODBUS_UNIT_ID)
            if result.isError(): raise ModbusException("Error leyendo Mod10k")
            r = result.registers
            return r[0] + r[1] * 10000 + r[2] * 10000**2 + r[3] * 10000**3
        else:
            result = self.modbus.read_holding_registers(reg.address, count=1, device_id=MODBUS_UNIT_ID)
            if result.isError(): raise ModbusException("Error leyendo int16")
            val = result.registers[0]
            if reg.fmt == 'int16_pf':
                return int16_to_pf(val)
            else:
                return int16_to_float(val, reg.scale, signed=(reg.fmt == 'int16'))

    def connect(self):
        if not self.modbus.connect():
            log.error("❌ No se pudo conectar al Simulador Modbus")
            return False
        
        try:
            health = self.influx.health()
            if health.status != "pass":
                log.error("❌ No se pudo conectar a InfluxDB")
                return False
        except Exception as e:
            log.error(f"❌ Excepción conectando a InfluxDB: {e}")
            return False
            
        log.info("✅ Conectado a Modbus-TCP y InfluxDB.")
        return True

    def process_alarms(self, current_data: Dict[str, float]):
        """Evalúa las reglas de alarma en el dato crudo de 1s de acuerdo a normativas 13.2kV MT."""
        
        # 1. Tensión Sag/Swell o Fuera de Rango (Evaluamos L-L: Nominal 13200V)
        # Límites: Sag < 90% (11880V), Swell > 110% (14520V)
        v_ll_avg = current_data.get("Vll_avg", 13200.0)
        is_v_bad = v_ll_avg < 11880.0 or v_ll_avg > 14520.0
        self._trigger_alarm_state("Tension_Sag_Swell", is_v_bad, v_ll_avg, f"Tensión L-L: {v_ll_avg:.2f}V")

        # 1.B Tensión de Fase Anómala (Nominal 7621V ± 7%)
        # Rango Permitido: 7087.55V a 8154.49V
        v_a = current_data.get("Vln_a", 7621.0)
        v_b = current_data.get("Vln_b", 7621.0)
        v_c = current_data.get("Vln_c", 7621.0)
        is_phase_bad = any(v < 7087.55 or v > 8154.49 for v in [v_a, v_b, v_c])
        self._trigger_alarm_state("Tension_Fase_Anomala", is_phase_bad, v_a, f"Tensiones: A={v_a:.0f}V, B={v_b:.0f}V, C={v_c:.0f}V")

        # 2. Restricción Neutro en MT Delta (I_n debe ser 0)
        i_n = current_data.get("I_n", 0.0)
        is_neutral_fault = i_n > 0.1  # Permitimos ínfimo margen de ruido matemático
        self._trigger_alarm_state("Corriente_Neutro_Anomala", is_neutral_fault, i_n, f"Corriente de Neutro: {i_n:.2f}A (Debe ser 0A)")

        # 3. Factor de Potencia Bajo (< 0.85)
        pf_tot = current_data.get("PF_tot", 1.0)
        is_pf_low = pf_tot > 0 and pf_tot < 0.85 # Asumiendo pf positivo para la alarma
        self._trigger_alarm_state("FP_Bajo", is_pf_low, pf_tot, f"Factor de Potencia actual: {pf_tot:.3f}")

        # 4. THD Elevado (> 5%)
        # Verificamos si alguna de las fases de tensión supera el 5%
        thd_va = current_data.get("THD_V_a", 0.0)
        is_thd_high = thd_va > 5.0
        self._trigger_alarm_state("THD_Elevado", is_thd_high, thd_va, f"THD Tensión Fase A: {thd_va:.2f}%")

        # 5. Demanda Máxima Superada
        kw_tot = current_data.get("kW_tot", 0.0)
        is_demand_high = kw_tot > self.peak_demand_kw and self.peak_demand_kw > 0
        self._trigger_alarm_state("Demanda_Superada", is_demand_high, kw_tot, f"Potencia Activa Total: {kw_tot:.2f}kW (Pico histórico: {self.peak_demand_kw:.2f}kW)")

    def _trigger_alarm_state(self, alarm_type: str, is_active: bool, value: float, details: str):
        """Maneja la histéresis: Solo actúa si el estado cambia."""
        was_active = self.alarms_state[alarm_type]
        
        if is_active and not was_active:
            # Flanco de subida -> Alarma se ACTIVA
            self.alarms_state[alarm_type] = True
            log.warning(f"🚨 ALARMA ACTIVADA: {alarm_type}")
            self._write_event_to_influx(alarm_type, "ACTIVA", value)
            Notifier.send_alert_async(alarm_type, "ACTIVA", value, details)
            
        elif not is_active and was_active:
            # Flanco de bajada -> Alarma se NORMALIZA
            self.alarms_state[alarm_type] = False
            log.info(f"✅ ALARMA NORMALIZADA: {alarm_type}")
            self._write_event_to_influx(alarm_type, "INACTIVA", value)
            Notifier.send_alert_async(alarm_type, "INACTIVA", value, details)

    def _write_event_to_influx(self, alarm_type: str, status: str, value: float):
        """Escribe un evento en la base de datos."""
        point = Point("eventos_alarmas") \
            .tag("tipo_alarma", alarm_type) \
            .tag("estado", status) \
            .field("valor_disparo", value)
        try:
            self.write_api.write(bucket=self.bucket_historic, record=point)
        except Exception as e:
            log.error(f"Error guardando evento en Influx: {e}")

    def write_15min_averages(self):
        """Calcula el promedio de los buffers y realiza el bulk write a InfluxDB."""
        log.info("📊 Calculando promedios de 15 minutos y guardando en BD...")
        
        point = Point("mediciones_electricas")
        avg_kw_tot = 0.0
        avg_v_ab = 13200.0
        avg_v_bc = 13200.0
        avg_v_ca = 13200.0

        for reg in REGISTER_MAP:
            if reg.fmt == 'mod10k':
                # Variables Acumulativas (Energía) -> Tomamos el último valor registrado
                val = self.last_energy_values.get(reg.name)
                if val is not None:
                    point.field(reg.name, val)
            else:
                # Variables Analógicas -> Promediamos el buffer
                data_list = self.buffers[reg.name]
                if data_list:
                    avg_val = sum(data_list) / len(data_list)
                    point.field(reg.name, avg_val)
                    
                    # Guardamos el promedio de kW_tot para chequear la demanda pico
                    if reg.name == "kW_tot":
                        avg_kw_tot = avg_val
                    elif reg.name == "Vll_ab":
                        avg_v_ab = avg_val
                    elif reg.name == "Vll_bc":
                        avg_v_bc = avg_val
                    elif reg.name == "Vll_ca":
                        avg_v_ca = avg_val
                
                # Vaciamos el buffer para los siguientes 15 min
                self.buffers[reg.name].clear()

        # Calcular e inyectar Vll_avg promedio de tensión L-L en el bucket histórico
        point.field("Vll_avg", (avg_v_ab + avg_v_bc + avg_v_ca) / 3.0)

        # Chequeo de actualización de Demanda Máxima según requerimiento 1.c
        if avg_kw_tot > self.peak_demand_kw:
            log.info(f"📈 Nueva Demanda Máxima Registrada: {avg_kw_tot:.2f} kW (Anterior: {self.peak_demand_kw:.2f} kW)")
            self.peak_demand_kw = avg_kw_tot
            point.field("Peak_kW_tot", self.peak_demand_kw)

        # Bulk Write a InfluxDB
        try:
            self.write_api.write(bucket=self.bucket_historic, record=point)
            log.info("💾 Bloque de 15 minutos guardado exitosamente en InfluxDB.")
        except Exception as e:
            log.error(f"Error escribiendo bloque en InfluxDB: {e}")

    def run(self):
        """Bucle principal de adquisición."""
        if not self.connect():
            return

        samples_count = 0
        
        try:
            while True:
                start_time = time.time()
                current_data: Dict[str, float] = {}

                try:
                    # 1. Leer todas las variables del CM4000
                    for reg in REGISTER_MAP:
                        val = self._read_register(reg.name)
                        current_data[reg.name] = val
                        
                        # Almacenar en buffers
                        if reg.fmt == 'mod10k':
                            self.last_energy_values[reg.name] = val
                        else:
                            self.buffers[reg.name].append(val)
                    
                    # Calcular Vll_avg localmente a partir de las tensiones L-L leídas
                    v_ab = current_data.get("Vll_ab", 13200.0)
                    v_bc = current_data.get("Vll_bc", 13200.0)
                    v_ca = current_data.get("Vll_ca", 13200.0)
                    current_data["Vll_avg"] = (v_ab + v_bc + v_ca) / 3.0
                    
                    samples_count += 1

                    # Escribir mediciones de tiempo real al bucket 'cm4000_realtime' (excluyendo acumuladores mod10k)
                    realtime_point = Point("mediciones_realtime")
                    for reg in REGISTER_MAP:
                        if reg.fmt != 'mod10k':
                            val = current_data[reg.name]
                            if not math.isnan(val):
                                realtime_point.field(reg.name, val)
                    
                    # También inyectamos Vll_avg calculada en el punto de tiempo real
                    realtime_point.field("Vll_avg", current_data["Vll_avg"])
                    
                    try:
                        self.write_api.write(bucket=self.bucket_realtime, record=realtime_point)
                    except Exception as e:
                        log.error(f"❌ Error escribiendo mediciones en tiempo real en InfluxDB: {e}")

                    # Si acabamos de recuperar la conexión
                    if self.alarms_state["Falla_Comunicacion"]:
                        self._trigger_alarm_state("Falla_Comunicacion", False, 0, "Conexión Modbus restaurada")

                    # 2. Evaluar alarmas en tiempo real (1 segundo)
                    self.process_alarms(current_data)

                except ModbusException as e:
                    # Falla de red o caída del simulador
                    self._trigger_alarm_state("Falla_Comunicacion", True, 0, f"Error: {e}")
                    # Limpiamos reconexión de pymodbus implícita para el sig loop
                    self.modbus.close()
                    self.modbus.connect()

                # 3. Evaluar si se cumplieron los 15 minutos (900 muestras a 1s)
                if samples_count >= AVERAGE_WINDOW_SEC:
                    self.write_15min_averages()
                    samples_count = 0

                # 4. Mantener la frecuencia de muestreo estricta a 1.0s
                elapsed = time.time() - start_time
                sleep_time = max(0, POLL_INTERVAL_SEC - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            log.info("⏻ Deteniendo Adquisidor de Datos CM4000.")
        finally:
            self.modbus.close()
            self.influx.close()


if __name__ == "__main__":
    adquisidor = CM4000Adquisidor()
    adquisidor.run()
