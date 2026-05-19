#!/bin/bash
echo "======================================================"
echo "    Instalando Dependencias del Dashboard IoT (HA)    "
echo "======================================================"

# Crear directorios si no existen
mkdir -p /home/maximo/IPSET/ha_config

# Asegurar permisos correctos (HA suele requerir permisos para escribir en /config)
chmod -R 777 /home/maximo/IPSET/ha_config

echo "Directorios de configuración creados y permisos asignados."

# Levantar el nuevo contenedor junto con los existentes
echo "Reiniciando el stack de Docker Compose para incluir Home Assistant..."
sudo docker compose up -d

echo "======================================================"
echo "Home Assistant ha sido desplegado exitosamente."
echo "Podrás acceder al Dashboard en: http://localhost:8123"
echo "Nota: El primer inicio de Home Assistant puede tardar"
echo "algunos minutos mientras prepara la base de datos local."
echo "======================================================"
