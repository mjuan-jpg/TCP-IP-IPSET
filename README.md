# CM4000 — Sistema de Monitoreo Eléctrico (Simulación)

Simulación de un medidor Schneider Electric PowerLogic CM4000 sobre Modbus-TCP,
con adquisición periódica de datos, almacenamiento en serie temporal y visualización
en InfluxDB.

---

## Arquitectura

```
Simulador CM4000          Adquisidor (Python)         InfluxDB
(Modbus-TCP :5020)  -->  (cm4000_client.py)  -->  (cm4000_data)
(Control TCP :5021)
```

---

## Stack tecnológico

| Componente | Tecnología | Puerto |
|---|---|---|
| Simulador CM4000 | Python / pymodbus | 5020 (Modbus), 5021 (Control) |
| Adquisición | Python (cm4000_client.py) | — |
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

### Capa de Datos y Adquisición Nativa (Python + InfluxDB)
- Reemplazamos Telegraf por un nodo de adquisición nativo en Python (`cm4000_client.py`).
- Implementamos buffers en memoria para realizar promedios matemáticos reales cada 15 minutos en variables analógicas.
- Añadimos un motor de alarmas en tiempo real (1s) con histéresis (Tensiones fuera de rango, sobrecorrientes, bajo FP, armónicos y corrientes de neutro anómalas) que envía eventos al instante a InfluxDB y notifica de forma asíncrona.
- Verificación y auditoría de límites físicos y regulatorios de Media Tensión (13.2 kV / 50 Hz).
