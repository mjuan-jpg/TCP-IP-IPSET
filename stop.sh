#!/bin/bash
# ==============================================================
#  CM4000 - Bajar Infraestructura Completa
# ==============================================================

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RED="\033[1;31m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "\n${BOLD}${RED}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${RED}║     CM4000 - Deteniendo Infraestructura       ║${RESET}"
echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════╝${RESET}\n"

cd "$SCRIPT_DIR"

echo -e "${YELLOW}[1/4] Exportando dashboard actual de Grafana al repositorio...${RESET}"
DASHBOARD_FILE="$SCRIPT_DIR/provisioning/dashboards/json/dashboard.json"
GRAFANA_API="http://localhost:3000/api/dashboards/uid/cm4000_mt_dashboard"
if curl -s --max-time 3 "$GRAFANA_API" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'dashboard' in data:
    with open('$DASHBOARD_FILE', 'w') as f:
        json.dump(data['dashboard'], f, indent=2, ensure_ascii=False)
    print('OK')
else:
    print('SKIP')
" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}      ✔ Dashboard exportado a provisioning/dashboards/json/dashboard.json${RESET}\n"
else
    echo -e "${YELLOW}      ⚠ Grafana no disponible, se conserva el JSON previo.${RESET}\n"
fi

echo -e "${YELLOW}[2/4] Deteniendo y eliminando contenedores...${RESET}"
docker compose down
echo -e "${GREEN}      ✔ Contenedores detenidos.${RESET}\n"

echo -e "${YELLOW}[3/4] Borrando datos de InfluxDB (volumen)...${RESET}"
docker volume rm ipset_influxdb_data 2>/dev/null && \
    echo -e "${GREEN}      ✔ Volumen eliminado. La próxima sesión arranca con datos limpios.${RESET}\n" || \
    echo -e "${GREEN}      ✔ El volumen ya no existía (ya estaba limpio).${RESET}\n"

echo -e "${YELLOW}[4/4] Estado final:${RESET}"
docker compose ps

echo -e "\n${BOLD}${RED}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${RED}║   Infraestructura DETENIDA correctamente.     ║${RESET}"
echo -e "${BOLD}${RED}║   Los datos de InfluxDB se conservaron.       ║${RESET}"
echo -e "${BOLD}${RED}║   Usa ./start.sh para volver a levantarla.   ║${RESET}"
echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════╝${RESET}\n"
