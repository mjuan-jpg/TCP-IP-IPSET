# Walkthrough: Simulador Modbus-TCP Schneider CM4000

Este documento describe la arquitectura y funcionamiento del simulador del medidor de energía **Schneider Electric PowerLogic CM4000**, el cual ha sido diseñado de forma modular utilizando Python y la librería `pymodbus`.

## 🏗️ Arquitectura del Sistema

El proyecto está compuesto por cinco componentes (archivos) principales que separan la lógica física, el protocolo de comunicación, el mapa de registros, y las interfaces de usuario. Esta separación permite que la simulación se ejecute en el fondo (como un demonio) y reciba comandos sin bloquearse.

### 1. `cm4000_registers.py` (El Mapa de Registros Oficial)
*   **Función:** Define de manera estricta todas las variables eléctricas (corrientes, voltajes L-L y L-N, potencias, THD, energías y peak demands) en sus direcciones Modbus correctas según el manual oficial de Schneider.
*   **Características Clave:**
    *   Soporte para múltiples formatos: `int16`, `uint16`, `int16_pf` y `mod10k` (Mod-10000 para acumuladores de energía).
    *   Aplicación automática de **Factores de Escala** (Scale Factors) para codificar y decodificar valores flotantes a registros de 16-bits de forma precisa (ej. corriente x10, frecuencia x100).

### 2. `cm4000_engine.py` (El Motor Físico y Estadístico)
*   **Función:** Es el núcleo que genera los datos dinámicos. Simula el comportamiento realista de una red industrial (por defecto, 380V / 50Hz).
*   **Características Clave:**
    *   **Generador de Ruido:** Utiliza distribuciones Gaussianas para inyectar fluctuaciones naturales en las lecturas y añade oscilaciones senoidales lentas para simular variaciones de carga reales.
    *   **Acumulación y Picos:** Mantiene un registro en tiempo real de los acumuladores de energía (`kWh`, `kVARh`) y captura automáticamente las demandas máximas (`Peak Demands`).
    *   **Manejo de Eventos (Fallos):** Es capaz de recibir e integrar eventos de calidad de energía (Sags, Swells, Armónicos, Pérdida de Fase, Overload, etc.) alterando matemáticamente las lecturas en tiempo real.

### 3. `cm4000_server.py` (El Servidor Modbus y Controlador TCP)
*   **Función:** Es el proceso principal que agrupa al motor físico y expone los datos hacia el exterior.
*   **Características Clave:**
    *   **Servidor Modbus (Puerto 5020 por defecto):** Utiliza la API `SimDevice` de `pymodbus` para levantar un servidor Modbus-TCP robusto en un loop asíncrono.
    *   **Thread Actualizador:** Un hilo en segundo plano que consulta constantemente al `cm4000_engine.py` (cada 1s), codifica los datos y actualiza los registros Modbus de manera "atómica".
    *   **Servidor de Control TCP (Puerto 5021 por defecto):** Un socket asíncrono independiente del protocolo Modbus. Está exclusivamente dedicado a recibir conexiones para inyección de eventos sin interferir en la red industrial.

### 4. `cm4000_control.py` (El Cliente de Inyección de Fallas)
*   **Función:** Se conecta remotamente al **Puerto de Control TCP (5021)** del simulador.
*   **Uso:** Permite al operador enviar comandos manuales (por TCP o Telnet) para estresar el sistema sin intervenir con la capa de adquisición de datos SCADA.
*   **Comandos Soportados:**
    *   `sag <fase> <profundidad%> <duración>` (Ej. `sag a 30 5`)
    *   `swell <fase> <incremento%> <duración>`
    *   `outage <duración>`
    *   `phase_loss <fase> <duración>`
    *   `harmonic <fase> <thd%> <duración>`
    *   `overload <fase> <factor> <duración>`
    *   `snapshot` (para ver las medidas actuales en el simulador)
    *   `status` (para ver los eventos o fallas activas).

### 5. `cm4000_client.py` (Nodo de Adquisición y Alertas)
*   **Función:** Reemplaza a Telegraf, actuando como el cerebro de adquisición de datos (SCADA/HMI) y motor de alertas con persistencia optimizada.
*   **Características Clave:** 
    *   **Polling Estricto:** Lee los registros Modbus crudos cada 1.0 segundos y decodifica la información.
    *   **Estrategia de Doble Bucket (Tiempo Real vs Histórico):**
        *   **Bucket de Tiempo Real (`cm4000_realtime`):** Recibe cada 1.0 segundo todas las variables analógicas instantáneas (ej. Freq, corrientes, tensiones, potencias activas/reactivas totales) mapeadas al measurement `mediciones_realtime`. Se excluyen explícitamente los acumuladores de energía codificados en `mod10k` (como `kWh_del` o `kVARh_del`) para evitar redundancia y desperdicio de almacenamiento. Este bucket cuenta con una política de retención corta de 1 hora (el mínimo admitido por InfluxDB v2) para auto-limpiar los datos de alta frecuencia.
        *   **Bucket Histórico (`cm4000_data`):** Almacena con retención infinita los consolidados de 15 minutos en el measurement `mediciones_electricas` (promediados matemáticamente) y los eventos en `eventos_alarmas`.
    *   **Alarmas en Tiempo Real:** Evalúa en cada segundo si se rompen límites operativos (Tensión fuera de rango, Sobrecorrientes, Bajo PF, armónicos) implementando una máquina de estados con histéresis y persistiendo los eventos en el bucket histórico.

### 6. Capa de Almacenamiento y Visualización (Docker Compose)
*   **Función:** Proporciona un entorno de ejecución continuo, base de datos de series temporales y visualización de paneles de control.
*   **Componentes Clave:**
    *   **Adquisidor Nativo:** El script `cm4000_client.py` se levanta en su propio contenedor (construido vía `Dockerfile.client`) asegurando que el proceso de lectura no dependa de factores externos.
    *   **InfluxDB v2:** Base de datos de series de tiempo (TSDB). Al inicializarse, crea el bucket histórico `cm4000_data` de forma nativa, y ejecuta un script de inicialización (`init-influxdb.sh` montado en `/docker-entrypoint-initdb.d/`) para aprovisionar automáticamente el segundo bucket `cm4000_realtime` con una política de retención de 1h.
    *   **Grafana:** Servidor de visualización expuesto en el puerto `3000:3000`. Carga automáticamente la conexión con InfluxDB mediante Flux a través del archivo de aprovisionamiento `provisioning/datasources/datasource.yml`. Adicionalmente, cuenta con el inicio de sesión anónimo con rol de Administrador (`GF_AUTH_ANONYMOUS_ENABLED=true` y `GF_AUTH_ANONYMOUS_ORG_ROLE=Admin`) para facilitar el diseño inmediato de tableros. El dashboard se aprovisiona desde `/etc/grafana/provisioning/dashboards/json/dashboard.json` de manera editable (`allowUiUpdates: true`).
    *   **Simulador Dockerizado:** El sistema se levanta desde un `Dockerfile` propio, empaquetando el motor y exponiendo sus puertos Modbus y TCP.
    *   **Orquestación y Sincronización en `start.sh` y `stop.sh`:**
        *   **Control de Versiones (Aprovisionamiento):** Para evitar que Grafana ignore los cambios del JSON al persistirse el volumen SQLite, `start.sh` incrementa automáticamente el campo `version` en `dashboard.json` antes de levantar Grafana. Esto engaña al motor de aprovisionamiento de Grafana para que sobrescriba su base de datos con el archivo actualizado.
        *   **Exportación Automatizada:** Al detener el stack mediante `stop.sh`, se realiza una llamada HTTP directa a la API local de Grafana para exportar la versión activa en memoria y sobreescribir el archivo `dashboard.json` del repositorio, manteniendo los cambios de la UI sincronizados en el código fuente.
        *   **Orden de Arranque:** Para evitar condiciones de carrera en el arranque, `start.sh` levanta primero el simulador y la base de datos, ejecuta un bucle de consulta (`polling loop`) hasta recibir `"status":"pass"` de InfluxDB, y solo entonces arranca el adquisidor y Grafana.


---

## 💡 Flujo de Operación Típico (Pipeline)

Para entender cómo operan todas las piezas juntas:

1.  **Levantar el Sistema (Fondo):** Se ejecuta `python cm4000_server.py`. Esto activa la simulación matemática de la red (`Engine`) y abre los puertos `5020` (Modbus) y `5021` (Control de Fallas).
2.  **Adquisición de Datos (Adquisidor):** El contenedor `adquisidor` (`cm4000_client.py`) se conecta vía Modbus, consulta registros cada 1s y alimenta sus buffers para la base de datos InfluxDB.
3.  **Inyectar Fallas Remotas:** En una terminal independiente, el ingeniero usa `python cm4000_control.py` conectándose al puerto 5021. Al emitir un comando como `sag a 30 10`:
    *   El comando viaja por TCP al `Server`.
    *   El `Server` lo inserta como evento activo en el `Engine`.
    *   El `Engine` altera el voltaje L-N, potencias y corrientes.
    *   El Cliente Adquisidor (`cm4000_client.py`) detecta la caída inmediatamente, registra la alarma de "Tensión Fuera de Rango" en InfluxDB y puede disparar notificaciones asíncronas.
