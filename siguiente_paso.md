# Plan de Acción: Capa de Adquisición y Almacenamiento

## Objetivo
Implementar la capa de adquisición de datos ("polling" periódico del servidor Modbus) y el almacenamiento de los registros simulados del CM4000 utilizando **Telegraf** e **InfluxDB**, según lo especificado en el diagrama de arquitectura del proyecto.

## Arquitectura Tecnológica
*   **Fuente de Datos**: Simulador CM4000 (Python, Modbus-TCP en puerto 5020).
*   **Capa de Adquisición**: **Telegraf**. Utilizaremos el plugin `inputs.modbus` para hacer peticiones periódicas (ej. cada 1 segundo) al servidor simulado y leer los registros.
*   **Capa de Almacenamiento**: **InfluxDB v2**. Base de datos de series temporales (TSDB) optimizada para la ingesta y guardado eficiente de métricas, que recibirá la telemetría enviada por Telegraf.
*   **Orquestación**: **Docker y Docker Compose** para levantar, configurar y comunicar los servicios de Telegraf e InfluxDB de forma limpia y reproducible sin instalar servicios directo en el host.

## Pasos de Implementación

### Fase 1: Entorno y Orquestación (Docker)
1.  **Crear archivo `docker-compose.yml`**: Definir los contenedores para InfluxDB (versión 2.x) y Telegraf.
2.  **Configurar directorios y volúmenes**: Crear carpetas locales para persistir la base de datos de InfluxDB y para alojar el archivo de configuración de Telegraf.

### Fase 2: Configuración Inicial de InfluxDB
1.  Levantar el contenedor de InfluxDB.
2.  Realizar el proceso de "Setup" inicial (desde la UI web en el puerto 8086):
    *   Crear una Organización (ej. `ipset`).
    *   Crear un Bucket de retención de datos (ej. `cm4000_data`).
    *   Generar un **API Token** con permisos de escritura, el cual requeriremos para que Telegraf pueda autenticarse y guardar los datos.

### Fase 3: Configuración del Agente Telegraf (`telegraf.conf`)
1.  Crear el archivo `telegraf.conf`.
2.  **Configurar Output (Salida)**: Activar y configurar el plugin `outputs.influxdb_v2` con la URL de InfluxDB, el Token, la Organización y el Bucket obtenidos en la Fase 2.
3.  **Configurar Input (Entrada Modbus)**: Configurar el plugin `inputs.modbus`.
    *   Ajustar conexión TCP hacia el simulador (IP del host y puerto 5020).
    *   Mapear exhaustivamente los registros de interés cruzando los datos con `cm4000_registers.py` (Voltajes V_A, V_B, V_C, Corrientes, Potencias, THD, Frecuencia, Energía).
    *   Configurar los tipos de registro (Holding Registers) y el factor de escala (Scale Factor) definido en nuestro proyecto para guardar en base de datos los valores reales con sus decimales correctos.

### Fase 4: Pruebas de Integración y Visualización
1.  Ejecutar el simulador (`python cm4000_server.py`).
2.  Levantar el stack completo de Docker (`docker-compose up -d`).
3.  Verificar los logs de Telegraf para confirmar lectura y escritura exitosa.
4.  Ingresar al *Data Explorer* dentro de la interfaz web de InfluxDB.
5.  Visualizar las primeras series temporales gráficamente.
6.  **Prueba Funcional de Eventos**: Utilizar `cm4000_control.py` para inyectar fallas (Sags, Swells) y verificar visualmente en las gráficas de InfluxDB que los eventos de caída o pico de tensión son detectados y almacenados con precisión en el tiempo.

## Siguiente Acción Sugerida
Para arrancar, podemos crear de inmediato la estructura de carpetas y el archivo `docker-compose.yml` base para tener listo el contenedor de InfluxDB.
