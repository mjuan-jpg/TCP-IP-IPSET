# CM4000 — Sistema de Monitoreo Eléctrico (Simulación)

Simulación de un medidor Schneider Electric PowerLogic CM4000 sobre Modbus-TCP, con adquisición periódica de datos, almacenamiento en serie temporal, estrategia de doble bucket y visualización integrada en Grafana.

---

## Arquitectura

```
Simulador CM4000          Adquisidor (Python)          InfluxDB v2
(Modbus-TCP :5020)  -->  (cm4000_client.py)   -->   ├── cm4000_data (Histórico 15m)
(Control TCP :5021)                                 └── cm4000_realtime (Tiempo Real 1s)
                                                           │
                                                           ▼
                                                       Grafana (Visualización :3000)
```

---

## Stack tecnológico

| Componente | Tecnología | Puerto | Descripción |
|---|---|---|---|
| **Simulador CM4000** | Python / pymodbus | 5020 (Modbus), 5021 (Control) | Simula el medidor físico y permite inyección de fallas. |
| **Adquisición** | Python (cm4000_client.py) | — | Polling cada 1.0s, procesamiento de promedios, alertas y persistencia. |
| **Almacenamiento** | InfluxDB 2.7 | 8086 | Motor de series temporales con buckets dedicados. |
| **Visualización** | Grafana OSS | 3000 | Dashboarding con login anónimo auto-configurado como Admin. |

---

## Uso rápido

```bash
# Levantar toda la infraestructura secuencialmente (Docker + abre InfluxDB y Grafana)
./start.sh

# Detener toda la infraestructura y limpiar volumen de datos
./stop.sh

# Inyectar fallas (sag, swell, transitorios, etc.)
python cm4000_control.py
```

---

## Hitos completados

### Modularización del Simulador CM4000
- Separamos la lógica principal del simulador de la inyección de fallos.
- Puerto de control TCP independiente (5021) y script dedicado `cm4000_control.py` para disparar eventos anómalos sin interrumpir el flujo de datos.

### Capa de Datos y Adquisición Nativa (Python + InfluxDB)
- Reemplazamos Telegraf por un nodo de adquisición nativo en Python (`cm4000_client.py`).
- Implementamos buffers en memoria para realizar promedios matemáticos reales cada 15 minutos en variables analógicas.
- Añadimos un motor de alarmas en tiempo real (1s) con histéresis (Tensiones fuera de rango, sobrecorrientes, bajo FP, armónicos y corrientes de neutro anómalas) que envía eventos al instante a InfluxDB y notifica de forma asíncrona.
- Verificación y auditoría de límites físicos y regulatorios de Media Tensión (13.2 kV / 50 Hz).

### Visualización y Persistencia Optimizada (Grafana + Estrategia Doble Bucket)
- **Integración con Grafana:** Añadimos el servicio en el puerto `3000` con aprovisionamiento automático del origen de datos a InfluxDB mediante Flux y habilitamos el inicio de sesión anónimo con privilegios de Administrador para facilitar el diseño inmediato de paneles.
- **Estrategia Doble Bucket:** 
  - `cm4000_data`: Para resúmenes históricos de 15 minutos y eventos de alarma con retención infinita.
  - `cm4000_realtime`: Para telemetría en tiempo real (1.0s) de variables analógicas críticas con retención corta de 1 hora (excluyendo acumuladores `mod10k` para conservar espacio).
- **Arranque Robusto:** Refactorizamos `start.sh` para sincronizar los inicios (espera la salud de InfluxDB antes de iniciar Grafana y el adquisidor) y abrir de forma automática ambas interfaces web en el navegador.
