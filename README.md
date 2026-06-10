# CM4000 — Sistema de Monitoreo Eléctrico (Simulación)

### 🚀 Guía de Clonación e Inicio (Desde Cero)
Si eres una persona nueva y deseas comenzar a trabajar con este repositorio, ejecuta los siguientes comandos para clonar y obtener la última versión actualizada:

```bash
# 1. Clonar el repositorio
git clone https://github.com/mjuan-jpg/TCP-IP-IPSET.git

# 2. Acceder al directorio del proyecto
cd TCP-IP-IPSET

# 3. Asegurar la rama principal y descargar los últimos cambios
git checkout main
git pull origin main
```

### 📖 [Manual del Operador en GitHub Pages](https://mjuan-jpg.github.io/TCP-IP-IPSET/)

Simulación de un medidor Schneider Electric PowerLogic CM4000 sobre Modbus-TCP, con adquisición periódica de datos, almacenamiento en serie temporal, estrategia de doble bucket, sistema de notificaciones y visualización integrada en Grafana.

---

## Arquitectura

```
Simulador CM4000          Adquisidor (Python)          InfluxDB v2
(Modbus-TCP :5020)  -->  (cm4000_client.py)   -->   ├── cm4000_data     (Histórico 90s)
(Control TCP :5021)           │                     ├── cm4000_realtime (Tiempo Real 1s)
                              │                     └── /metrics        (Métricas Internas)
                              ▼                                 │
                    cm4000_notifier.py                          ▼
                    (Telegram + Email)                  Prometheus :9090  <-- cAdvisor :8080
                                                                │
                                                                ▼
                                                        Grafana :3000
                                                        (Dashboards)
```

---

## Stack tecnológico

| Componente | Tecnología | Puerto | Descripción |
|---|---|---|---|
| **Simulador CM4000** | Python / pymodbus | 5020 (Modbus), 5021 (Control) | Simula el medidor físico y permite inyección de fallas vía TCP. |
| **Adquisidor** | Python (`cm4000_client.py`) | — | Polling cada 1.0 s, promedios cada 90 s, motor de alarmas con histéresis pura. |
| **Notificador** | Python (`cm4000_notifier.py`) | — | Despacha alertas por Telegram y Email en hilos fire-and-forget. |
| **Almacenamiento** | InfluxDB 2.7 | 8086 | Motor de series temporales con buckets dedicados. |
| **Observabilidad** | Prometheus + cAdvisor | 9090 / 8080 | Telemetría de infraestructura (CPU, RAM, Volumen de BD). |
| **Visualización** | Grafana OSS | 3000 | Dashboards aprovisionados con login anónimo Admin y banners dinámicos. |

---

## Imágenes Docker Hub

Las imágenes del simulador y del adquisidor están publicadas en Docker Hub:

| Imagen | Hub |
|---|---|
| Simulador | `maximodockerhub/cm4000-simulator:latest` |
| Adquisidor | `maximodockerhub/cm4000-adquisidor:latest` |

> `start.sh` hace `docker compose pull` automáticamente al arrancar.

---

## Inicio rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/mjuan-jpg/TCP-IP-IPSET.git
cd TCP-IP-IPSET
git checkout main
git pull origin main

# 2. Configurar credenciales de notificaciones (opcional)
cp .env.template .env   # completar con tokens de Telegram y SMTP

# 3. Levantar la infraestructura completa
./start.sh

# 4. Detener (exporta el dashboard antes de bajar)
./stop.sh

# 5. Inyectar fallas manualmente
python cm4000_control.py
```

---

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram (desde @BotFather) |
| `TELEGRAM_CHAT_ID` | ID del chat/grupo receptor |
| `SMTP_HOST` | Servidor SMTP (default: `smtp.gmail.com`) |
| `SMTP_PORT` | Puerto SMTP (default: `587`) |
| `SMTP_USER` | Usuario/cuenta de correo |
| `SMTP_PASSWORD` | App Password de Gmail |
| `NOTIFY_EMAIL_TO` | Destinatarios (separados por coma) |

---

## Motor de Alarmas — Histéresis Pura

El adquisidor evalúa 7 reglas normativas cada segundo. Solo actúa en **transición de estado** (sin cooldown ni re-alertas):

| Alarma | Condición de disparo |
|---|---|
| `Tension_Sag_Swell` | `Vll_avg < 11 880 V` ó `> 14 520 V` |
| `Tension_Fase_Anomala` | Cualquier `Vln` fuera de `7 088–8 154 V` (±7%) |
| `Corriente_Neutro_Anomala` | `I_n > 0.1 A` |
| `Sobrecorriente` | Cualquier fase `I > 120 A` |
| `FP_Bajo` | `PF_tot < 0.85` |
| `THD_Elevado` | `THD_V_a > 5.0%` (EN 50160) |
| `Demanda_Superada` | `kW_tot > pico histórico` (desde ventana #2) |
| `Falla_Comunicacion` | `ModbusException` capturada |

---

## Hitos completados

- **Simulador modular** con puerto de control TCP independiente (5021)
- **Adquisidor nativo Python** reemplazando Telegraf
- **Estrategia doble bucket** (realtime 1 s + histórico 90 s)
- **Motor de alarmas con histéresis pura** + notificaciones Telegram/Email
- **Dashboard Grafana** con tensiones y corrientes por fase, colores dinámicos por umbral
- **Bitácora de alarmas** con estado ACTIVA/INACTIVA en tiempo real
- **Ciclo de vida automatizado**: `start.sh` (pull + health check + versionado) / `stop.sh` (export + down)
- **Imágenes publicadas en Docker Hub** — despliegue sin compilación local
- **Observabilidad de Infraestructura**: Stack Prometheus + cAdvisor monitoreando CPU/RAM de contenedores y tamaño neto (TSM+WAL) del volumen de InfluxDB.
- **Banner personalizado en Grafana** mediante panel de texto con imagen inyectada en Base64.
