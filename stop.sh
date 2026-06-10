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

# ── 1. Exportar dashboards antes de bajar Grafana ─────────────
echo -e "${YELLOW}[1/4] Exportando dashboards actuales de Grafana al repositorio...${RESET}"

# Mapa: UID del dashboard -> ruta local del archivo JSON
declare -A DASHBOARD_MAP=(
    ["cm4000_mt_dashboard"]="$SCRIPT_DIR/provisioning/dashboards/json/dashboard.json"
    ["infra-observability"]="$SCRIPT_DIR/provisioning/dashboards/json/infra.json"
)

GRAFANA_BASE="http://localhost:3000"
EXPORT_OK=0

for UID_KEY in "${!DASHBOARD_MAP[@]}"; do
    TARGET_FILE="${DASHBOARD_MAP[$UID_KEY]}"
    API_URL="$GRAFANA_BASE/api/dashboards/uid/$UID_KEY"

    if curl -s --max-time 5 "$API_URL" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'dashboard' in data:
    with open('$TARGET_FILE', 'w') as f:
        json.dump(data['dashboard'], f, indent=2, ensure_ascii=False)
    print('OK')
else:
    print('SKIP')
" 2>/dev/null | grep -q "OK"; then
        echo -e "${GREEN}      ✔ [$UID_KEY] → $(basename "$TARGET_FILE")${RESET}"
        EXPORT_OK=$((EXPORT_OK + 1))
    else
        echo -e "${YELLOW}      ⚠ [$UID_KEY] Grafana no disponible, se conserva el JSON previo.${RESET}"
    fi
done

echo -e "${GREEN}      → $EXPORT_OK/2 dashboard(s) exportados exitosamente.${RESET}\n"

# ── 2. Incrementar versión de dashboards para forzar re-provisión ─
echo -e "${YELLOW}[2/4] Incrementando versión de dashboards para bypass de caché...${RESET}"
for JSON_FILE in "$SCRIPT_DIR/provisioning/dashboards/json/"*.json; do
    python3 -c "
import sys, json
with open('$JSON_FILE', 'r') as f:
    data = json.load(f)
data['version'] = data.get('version', 1) + 1
with open('$JSON_FILE', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('v' + str(data['version']))
" 2>/dev/null && echo -e "${GREEN}      ✔ $(basename "$JSON_FILE") → versión actualizada${RESET}" \
              || echo -e "${YELLOW}      ⚠ No se pudo actualizar $(basename "$JSON_FILE")${RESET}"
done
echo ""

# ── 3. Detener y eliminar contenedores ────────────────────────
echo -e "${YELLOW}[3/4] Deteniendo y eliminando contenedores...${RESET}"
docker compose down
echo -e "${GREEN}      ✔ Contenedores detenidos.${RESET}\n"

# ── 4. Estado final ───────────────────────────────────────────
echo -e "${YELLOW}[4/4] Estado final:${RESET}"
docker compose ps

echo -e "\n${BOLD}${RED}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${RED}║   Infraestructura DETENIDA correctamente.     ║${RESET}"
echo -e "${BOLD}${RED}║   Datos InfluxDB conservados en volumen.      ║${RESET}"
echo -e "${BOLD}${RED}║   Usa ./start.sh para volver a levantarla.   ║${RESET}"
echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════╝${RESET}\n"
