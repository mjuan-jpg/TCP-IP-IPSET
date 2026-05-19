# CM4000 — Sistema de Monitoreo Eléctrico (Simulación)

Simulación de un medidor Schneider Electric PowerLogic CM4000 sobre Modbus-TCP,
con adquisición periódica de datos, almacenamiento en serie temporal y visualización
en InfluxDB.

---

## Arquitectura

```
Simulador CM4000          Telegraf               InfluxDB
(Modbus-TCP :5020)  -->  (polling Modbus)  -->  (cm4000_data)
(Control TCP :5021)
```

---

## Stack tecnológico

| Componente | Tecnología | Puerto |
|---|---|---|
| Simulador CM4000 | Python / pymodbus | 5020 (Modbus), 5021 (Control) |
| Adquisición | Telegraf 1.28 | — |
| Almacenamiento | InfluxDB 2.7 | 8086 |

---

## Uso rápido

```bash
# Levantar toda la infraestructura (Docker + abre InfluxDB)
./start.sh

# Detener toda la infraestructura
./stop.sh

# Inyectar fallas (sag, swell, etc.)
python cm4000_control.py
```

---

## Hitos completados

### Modularización del Simulador CM4000
- Separamos la lógica principal del simulador de la inyección de fallos.
- Puerto de control TCP independiente (5021) y script dedicado `cm4000_control.py`
  para disparar eventos anómalos sin interrumpir el flujo de datos hacia Telegraf.

### Capa de Datos con InfluxDB y Telegraf
- Contenerización de InfluxDB y Telegraf usando Docker Compose.
- Telegraf consulta periódicamente los registros Modbus del simulador y los almacena
  en la base de datos de series temporales.
- Verificación de parámetros eléctricos e inyecciones de eventos (sags/swells)
  registrados correctamente en InfluxDB.
