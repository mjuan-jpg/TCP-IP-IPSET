#!/bin/bash
set -e

# Crear el bucket secundario de tiempo real.
# NOTA: Aunque el requerimiento especifica una retención de 5m (300s), InfluxDB v2 
# impone un límite mínimo estricto de 1 hora (1h o 3600s) para la política de retención.
# Cualquier valor inferior causa un error 500: "retention policy duration must be at least 1h0m0s".
# Configurado a 1h para evitar fallos de inicialización.
influx bucket create \
  -n cm4000_realtime \
  -o "${DOCKER_INFLUXDB_INIT_ORG}" \
  -r 1h
