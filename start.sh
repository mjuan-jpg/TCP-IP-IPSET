#!/bin/bash
# ==============================================================
#  CM4000 - Levantar Infraestructura Completa
# ==============================================================

set -e

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RED="\033[1;31m"
RESET="\033[0m"

INFLUX_URL="http://localhost:8086"
HA_URL="http://localhost:8123"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "\n${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║     CM4000 - Iniciando Infraestructura        ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

# ── 1. Levantar contenedores ──────────────────────────────────
echo -e "${YELLOW}[1/4] Levantando contenedores Docker...${RESET}"
cd "$SCRIPT_DIR"
docker compose up -d --build
echo -e "${GREEN}      ✔ Contenedores en marcha.${RESET}\n"

# ── 2. Esperar a que InfluxDB esté listo ─────────────────────
echo -e "${YELLOW}[2/4] Esperando que InfluxDB esté disponible...${RESET}"
until curl -s "$INFLUX_URL/health" | grep -q '"status":"pass"'; do
    echo -e "      ⏳ Aún no disponible, reintentando en 3s..."
    sleep 3
done
echo -e "${GREEN}      ✔ InfluxDB listo en ${INFLUX_URL}${RESET}\n"

# ── 3. Esperar a que Home Assistant esté listo ───────────────
echo -e "${YELLOW}[3/4] Esperando que Home Assistant esté disponible...${RESET}"
until curl -s -o /dev/null -w "%{http_code}" "$HA_URL" | grep -qE "^(200|301|302)$"; do
    echo -e "      ⏳ Aún no disponible, reintentando en 5s..."
    sleep 5
done
echo -e "${GREEN}      ✔ Home Assistant listo en ${HA_URL}${RESET}\n"

# ── 4. Abrir navegador ────────────────────────────────────────
echo -e "${YELLOW}[4/4] Abriendo interfaces en el navegador...${RESET}"
sleep 1
xdg-open "$INFLUX_URL" 2>/dev/null || true
sleep 1
xdg-open "$HA_URL" 2>/dev/null || true
echo -e "${GREEN}      ✔ Navegador lanzado.${RESET}\n"

# ── Log en tiempo real ────────────────────────────────────────
echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   Infraestructura ACTIVA - Log en tiempo real  ║${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  InfluxDB:       ${INFLUX_URL}${RESET}"
echo -e "${CYAN}║  Home Assistant: ${HA_URL}${RESET}"
echo -e "${BOLD}${CYAN}╠═══════════════════════════════════════════════╣${RESET}"
echo -e "${CYAN}║  Ctrl+C para dejar de ver logs (infra sigue   ║${RESET}"
echo -e "${CYAN}║  corriendo). Usa ./stop.sh para detenerla.    ║${RESET}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"

docker compose logs -f --tail=50
