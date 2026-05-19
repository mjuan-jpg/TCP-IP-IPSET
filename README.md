# Estado del Proyecto: Sistema de Monitoreo CM4000

## Dashboard IoT y Automatizaciones en Home Assistant (lo más reciente):
- Estuvimos integrando Home Assistant dentro del stack de simulación.
- Trabajamos en conectar InfluxDB como fuente de datos y configuramos el dashboard Lovelace (archivos `ui-lovelace.yaml` y `configuration.yaml`) para visualizar la telemetría eléctrica en tiempo real.
- También estuvimos ajustando las alertas automáticas basadas en la severidad de los eventos (archivo `automations.yaml`).

## Capa de Datos con InfluxDB y Telegraf:
- Contenerizamos InfluxDB y Telegraf usando Docker Compose.
- Configuramos Telegraf para que consulte periódicamente los registros Modbus del simulador y los almacene en la base de datos de series temporales.
- Verificamos que los parámetros eléctricos y las inyecciones de eventos (como sags o swells) se registraran correctamente.

## Modularización del Simulador CM4000:
- Separamos la lógica principal del simulador de la inyección de fallos.
- Creamos un puerto de control TCP independiente (5021) y un script dedicado (`cm4000_control.py`) para disparar eventos anómalos de forma remota sin interrumpir el flujo constante de datos hacia el sistema SCADA/Telegraf.
