# CM4000 — Sistema de Monitoreo Eléctrico (Simulación)

Simulación de un medidor Schneider Electric PowerLogic CM4000 sobre Modbus-TCP, con adquisición periódica de datos, almacenamiento en serie temporal, estrategia de doble bucket y visualización integrada en Grafana.

---

## Arquitectura

```
Simulador CM4000          Adquisidor (Python)          InfluxDB v2
(Modbus-TCP :5020)  -->  (cm4000_client.py)   -->   ├── cm4000_data (Histórico 90s)
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
| **Adquisición** | Python (cm4000_client.py) | — | Polling cada 1.0s, promedios cada 90s, motor de alarmas con histéresis y persistencia. |
| **Almacenamiento** | InfluxDB 2.7 | 8086 | Motor de series temporales con buckets dedicados. |
| **Visualización** | Grafana OSS | 3000 | Dashboard pre-aprovisionado con login anónimo Admin, persistencia de cambios UI automatizada. |

---

## Uso rápido

```bash
# Levantar toda la infraestructura (compila imágenes + abre InfluxDB y Grafana)
./start.sh

# Detener toda la infraestructura y exportar dashboard al repositorio
./stop.sh

# Inyectar fallas (sag, swell, transitorios, outage, etc.)
python cm4000_control.py
```

---

## Hitos completados

### Modularización del Simulador CM4000
- Separamos la lógica principal del simulador de la inyección de fallos.
- Puerto de control TCP independiente (5021) y script dedicado `cm4000_control.py` para disparar eventos anómalos sin interrumpir el flujo de datos.

### Capa de Datos y Adquisición Nativa (Python + InfluxDB)
- Reemplazamos Telegraf por un nodo de adquisición nativo en Python (`cm4000_client.py`).
- Implementamos buffers en memoria para realizar promedios matemáticos reales cada **90 segundos** en variables analógicas.
- Motor de alarmas en tiempo real (1s) con histéresis (Tensiones fuera de rango, sobrecorrientes, bajo FP, armónicos y corrientes de neutro anómalas) que envía eventos al instante a InfluxDB.
- Verificación y auditoría de límites físicos y regulatorios de Media Tensión (13.2 kV / 50 Hz, EN 50160).

### Visualización y Persistencia Optimizada (Grafana + Estrategia Doble Bucket)
- **Integración con Grafana:** Servicio en el puerto `3000` con aprovisionamiento automático del datasource InfluxDB Flux y login anónimo con rol Administrador.
- **Estrategia Doble Bucket:**
  - `cm4000_data`: Resúmenes históricos de 90s y eventos de alarma con retención infinita.
  - `cm4000_realtime`: Telemetría instantánea (1.0s) con retención de 1h (excluyendo acumuladores `mod10k`).
- **Dashboard Pre-aprovisionado:** Panel completo con gráficas de tensiones línea a línea, corrientes por fase, potencias, factor de potencia, THD y bitácora de alarmas.

### Bitácora de Alarmas (Registro de Eventos)
- Panel `🚨 Registro de Alarmas` con tabla de 4 columnas: `⏱ Fecha/Hora`, `⚡ Tipo de Alarma`, `🔔 Estado`, `📈 Valor`.
- Estado `ACTIVA` → fondo rojo | `INACTIVA` → fondo verde.
- Consulta Flux con `|> group()` para aplanar las series tagueadas de InfluxDB en una tabla plana sin columnas fragmentadas.

### Ciclo de Vida del Dashboard (Persistencia de Cambios)
- **`stop.sh`:** Antes de detener los contenedores, exporta automáticamente el dashboard activo desde la API de Grafana al archivo `provisioning/dashboards/json/dashboard.json`, preservando cualquier edición visual realizada en la UI.
- **`start.sh`:** Auto-incrementa el campo `version` del JSON antes de levantar Grafana, forzando que el motor de aprovisionamiento sobrescriba la base de datos SQLite interna con el archivo actualizado.
- **`allowUiUpdates: true`:** El dashboard es editable desde la UI de Grafana sin restricciones.

### Arranque Robusto con Compilación Automática
- `start.sh` compila las imágenes Docker en cada arranque (`--build`) para garantizar que los cambios en los scripts Python se apliquen siempre sin pasos manuales adicionales.
- Orden de arranque secuencial: Simulador + InfluxDB → espera health check → incremento de versión del dashboard → Adquisidor + Grafana → apertura de navegadores.
