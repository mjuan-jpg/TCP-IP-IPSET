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

echo -e "${YELLOW}[1/3] Deteniendo y eliminando contenedores...${RESET}"
docker compose down
echo -e "${GREEN}      ✔ Contenedores detenidos.${RESET}\n"

echo -e "${YELLOW}[2/3] Borrando datos de InfluxDB (volumen)...${RESET}"
docker volume rm ipset_influxdb_data 2>/dev/null && \
    echo -e "${GREEN}      ✔ Volumen eliminado. La próxima sesión arranca con datos limpios.${RESET}\n" || \
    echo -e "${GREEN}      ✔ El volumen ya no existía (ya estaba limpio).${RESET}\n"

echo -e "${YELLOW}[3/3] Estado final:${RESET}"
docker compose ps

echo -e "\n${BOLD}${RED}╔═══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${RED}║   Infraestructura DETENIDA correctamente.     ║${RESET}"
echo -e "${BOLD}${RED}║   Los datos de InfluxDB se conservaron.       ║${RESET}"
echo -e "${BOLD}${RED}║   Usa ./start.sh para volver a levantarla.   ║${RESET}"
echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════╝${RESET}\n"
