#!/bin/bash
# Este script instala Docker y Docker Compose.
# Debes ejecutarlo con permisos de administrador (sudo).

echo "1. Limpiando el repositorio problemático de InfluxData que causó el error..."
rm -f /etc/apt/sources.list.d/influxdata.list
apt-get update

echo "2. Instalando Docker y Docker Compose..."
# Usamos el script oficial de instalación de Docker que funciona en todas las versiones de Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

echo "3. Limpiando archivos temporales..."
rm -f get-docker.sh

echo "======================================================"
echo "Dependencias instaladas exitosamente."
echo "Ahora puedes levantar la infraestructura ejecutando:"
echo "sudo docker compose up -d"
echo "======================================================"
