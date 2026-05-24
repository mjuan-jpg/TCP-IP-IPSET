#!/bin/bash
# ==============================================================
#  CM4000 - Levantar Infraestructura Completa
# ==============================================================

set -e

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RESET="\033[0m"

INFLUX_URL="http://localhost:8086"
GRAFANA_URL="http://localhost:3000"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "\n${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║     CM4000 - Iniciando Infraestructura        ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

# ── 1. Levantar infraestructura base ──────────────────────────
echo -e "${YELLOW}[1/3] Compilando imágenes y levantando base de infraestructura (simulador e influxdb)...${RESET}"
cd "$SCRIPT_DIR"
docker compose up -d --build simulator influxdb
echo -e "${GREEN}      ✔ Contenedores base en marcha.${RESET}\n"

# ── 2. Esperar a que InfluxDB esté listo ─────────────────────
echo -e "${YELLOW}[2/3] Esperando que InfluxDB esté disponible...${RESET}"
until curl -s "$INFLUX_URL/health" | grep -q '"status":"pass"'; do
    echo -e "      ⏳ Aún no disponible, reintentando en 3s..."
    sleep 3
done
echo -e "${GREEN}      ✔ InfluxDB listo en ${INFLUX_URL}${RESET}\n"

# ── 2.5. Incrementar versión del dashboard para forzar aprovisionamiento ────
echo -e "${YELLOW}[2.5] Incrementando versión del dashboard.json para forzar aprovisionamiento...${RESET}"
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

# ── 3. Levantar adquisidor y Grafana ──────────────────────────────────────
echo -e "${YELLOW}[3/4] Compilando imagen del adquisidor y levantando Grafana...${RESET}"
docker compose up -d --build adquisidor grafana
echo -e "${GREEN}      ✔ Adquisidor y Grafana en marcha.${RESET}\n"

# ── 4. Abrir navegador ────────────────────────────────────────
echo -e "${YELLOW}[4/4] Abriendo InfluxDB y Grafana en el navegador...${RESET}"
sleep 1
xdg-open "$INFLUX_URL" 2>/dev/null || true
xdg-open "$GRAFANA_URL" 2>/dev/null || true
echo -e "${GREEN}      ✔ Navegadores lanzados.${RESET}\n"

# ── Log en tiempo real ────────────────────────────────────────
echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   Infraestructura ACTIVA - Log en tiempo real  ║${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  InfluxDB:  ${INFLUX_URL}                  ${RESET}"
echo -e "${CYAN}║  Grafana:   ${GRAFANA_URL}                   ${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  Ctrl+C para dejar de ver logs (infra sigue   ║${RESET}"
echo -e "${CYAN}║  corriendo). Usa ./stop.sh para detenerla.    ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

docker compose logs -f --tail=50 simulator adquisidor
