#!/bin/bash
# ==============================================================
#  CM4000 - Levantar Infraestructura Completa
#  Imágenes pre-construidas desde Docker Hub (maximodockerhub)
# ==============================================================

set -e

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

INFLUX_URL="http://localhost:8086"
GRAFANA_URL="http://localhost:3000/d/cm4000_mt_dashboard/monitoreo-electrico-cm4000-media-tension?orgId=1&from=now-15m&to=now&timezone=browser&refresh=5s"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "\n${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║     CM4000 - Iniciando Infraestructura        ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

# ── 0. Preparar directorios y volúmenes ───────────────────────
echo -e "${YELLOW}[0/4] Verificando directorios y volúmenes de almacenamiento...${RESET}"

# grafana_data es un bind mount: debe existir en el host antes de levantar Grafana.
# En una PC nueva (o clon del repo) este directorio no existe → Docker falla al montar.
if [ ! -d "$SCRIPT_DIR/grafana_data" ]; then
    mkdir -p "$SCRIPT_DIR/grafana_data"
    echo -e "      📁 Directorio grafana_data creado."
else
    echo -e "      📁 grafana_data ya existe."
fi

# Volúmenes nombrados de Docker (influxdb_data, prometheus_data).
# Docker Compose los crea al hacer 'up', pero pre-crearlos evita
# condiciones de carrera si el demonio aún no está listo.
for VOL in influxdb_data prometheus_data; do
    if ! docker volume inspect "$VOL" > /dev/null 2>&1; then
        docker volume create "$VOL" > /dev/null
        echo -e "      💾 Volumen Docker '${VOL}' creado."
    else
        echo -e "      💾 Volumen Docker '${VOL}' ya existe."
    fi
done

echo -e "${GREEN}      ✔ Almacenamiento listo.${RESET}\\n"

# ── 1. Verificar archivo .env ──────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${YELLOW}      ⚠ No se encontró .env — las notificaciones Telegram/Email estarán desactivadas.${RESET}"
    echo -e "${YELLOW}        Crea el archivo .env con tus credenciales para activarlas.${RESET}\n"
fi

# ── 2. Pull de imágenes desde Docker Hub ──────────────────────
echo -e "${YELLOW}[1/4] Descargando imágenes desde Docker Hub...${RESET}"
cd "$SCRIPT_DIR"
docker compose pull simulator adquisidor
echo -e "${GREEN}      ✔ Imágenes actualizadas.${RESET}\n"

# ── 3. Levantar simulador e InfluxDB ──────────────────────────
echo -e "${YELLOW}[2/4] Levantando simulador e InfluxDB...${RESET}"
docker compose up -d simulator influxdb
echo -e "${GREEN}      ✔ Contenedores base en marcha.${RESET}\n"

# ── 4. Esperar a que InfluxDB esté listo ──────────────────────
echo -e "${YELLOW}[3/4] Esperando que InfluxDB esté disponible...${RESET}"
until curl -s "$INFLUX_URL/health" | grep -q '"status":"pass"'; do
    echo -e "      ⏳ Aún no disponible, reintentando en 3s..."
    sleep 3
done
echo -e "${GREEN}      ✔ InfluxDB listo en ${INFLUX_URL}${RESET}\n"

# ── 4.5. Incrementar versión del dashboard ────────────────────
echo -e "${YELLOW}[3.5/4] Incrementando versión del dashboard para forzar aprovisionamiento...${RESET}"
python3 -c "
import json, os
path = '$SCRIPT_DIR/provisioning/dashboards/json/dashboard.json'
with open(path) as f:
    d = json.load(f)
d['version'] = d.get('version', 1) + 1
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print(f\"      version → {d['version']}\")
"
echo -e "${GREEN}      ✔ Versión del dashboard actualizada.${RESET}\n"

# ── 5. Levantar adquisidor y Grafana ──────────────────────────
echo -e "${YELLOW}[4/4] Levantando adquisidor y Grafana...${RESET}"
docker compose up -d adquisidor grafana
echo -e "${GREEN}      ✔ Adquisidor y Grafana en marcha.${RESET}\n"

# ── 6. Abrir navegador ────────────────────────────────────────
sleep 2
xdg-open "$INFLUX_URL" 2>/dev/null || true
xdg-open "$GRAFANA_URL" 2>/dev/null || true

# ── Info final ────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   Infraestructura ACTIVA - Log en tiempo real  ║${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  InfluxDB : http://localhost:8086              ║${RESET}"
echo -e "${CYAN}║  Grafana  : http://localhost:3000              ║${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  Ctrl+C para dejar de ver logs (infra sigue   ║${RESET}"
echo -e "${CYAN}║  corriendo). Usa ./stop.sh para detenerla.    ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

docker compose logs -f --tail=50 simulator adquisidor
