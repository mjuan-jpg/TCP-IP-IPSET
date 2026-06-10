# Walkthrough: Simulador Modbus-TCP Schneider CM4000

Este documento describe la arquitectura y funcionamiento del simulador del medidor de energía **Schneider Electric PowerLogic CM4000**, el cual ha sido diseñado de forma modular utilizando Python y la librería `pymodbus`. A partir de la rama **`Observabilidad`**, el stack incorpora una capa completa de telemetría de infraestructura basada en **cAdvisor** y **Prometheus**.

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

### 6. Capa de Almacenamiento, Visualización y Observabilidad (Docker Compose)
*   **Función:** Proporciona un entorno de ejecución continuo, base de datos de series temporales, visualización de paneles de control y **telemetría de infraestructura de contenedores**.
*   **Red Virtual:** Todos los servicios pertenecen a la red `red_gestion` (bridge con salida externa), lo que garantiza resolución DNS interna entre contenedores (por ejemplo, `prometheus` puede resolver `cadvisor:8080` sin exponer puertos entre redes).
*   **Nomenclatura de Contenedores:** Los `container_name` de los servicios de negocio están alineados con su nombre de servicio Compose (`simulator`, `adquisidor`, `base_datos`, `dashboard`) para garantizar que las etiquetas `container_label_com_docker_compose_service` expuestas por cAdvisor sean coherentes con las consultas PromQL del dashboard de infraestructura.
*   **Componentes Clave:**
    *   **Adquisidor Nativo (`adquisidor`):** El script `cm4000_client.py` se levanta en su propio contenedor (construido vía `Dockerfile.client`) asegurando que el proceso de lectura no dependa de factores externos.
    *   **InfluxDB v2 (`base_datos`):** Base de datos de series de tiempo (TSDB). Al inicializarse, crea el bucket histórico `cm4000_data` de forma nativa, y ejecuta un script de inicialización (`init-influxdb.sh` montado en `/docker-entrypoint-initdb.d/`) para aprovisionar automáticamente el segundo bucket `cm4000_realtime` con una política de retención de 1h.
    *   **Grafana (`dashboard`):** Servidor de visualización expuesto en el puerto `3000:3000`. Carga automáticamente la conexión con InfluxDB mediante Flux (`provisioning/datasources/datasource.yml`) **y con Prometheus** (`provisioning/datasources/prometheus-datasource.yml`). Cuenta con inicio de sesión anónimo con rol Administrador. Aprovisiona dos dashboards desde `provisioning/dashboards/json/`: `dashboard.json` (eléctrico) e `infra.json` (infraestructura).
    *   **Simulador Dockerizado (`simulator`):** Empaqueta el motor y expone los puertos Modbus (5020) y Control TCP (5021).
    *   **cAdvisor (`cadvisor`):** Agente de telemetría de contenedores de Google. Corre en modo `privileged` para acceder a métricas de `cgroup v2` y estadísticas de red. Monta el sistema de archivos del host en modo solo lectura (`:ro`) y expone las métricas en `http://cadvisor:8080/metrics`.
    *   **Prometheus (`prometheus`):** Motor de scraping y base de datos de métricas de infraestructura (TSDB separada de InfluxDB). Recolecta métricas de `cadvisor:8080` cada 15 segundos y las persiste en el volumen `prometheus_data` con retención de 30 días. Expuesto localmente en `http://localhost:9090`.
    *   **Orquestación y Sincronización en `start.sh` y `stop.sh`:**
        *   **Control de Versiones (Aprovisionamiento):** Para evitar que Grafana ignore los cambios del JSON al persistirse el volumen SQLite, `start.sh` incrementa automáticamente el campo `version` en todos los archivos JSON de `provisioning/dashboards/json/` antes de levantar Grafana.
        *   **Exportación Automatizada Dual:** Al detener el stack mediante `stop.sh`, se realizan llamadas HTTP a la API de Grafana para exportar la versión activa en memoria de **ambos dashboards** (`cm4000_mt_dashboard` e `infra-observability`) a sus respectivos archivos JSON, manteniendo los cambios de la UI sincronizados en el código fuente.
        *   **Orden de Arranque:** Para evitar condiciones de carrera, `start.sh` levanta primero el simulador y la base de datos, ejecuta un bucle de consulta (`polling loop`) hasta recibir `"status":"pass"` de InfluxDB, y solo entonces arranca el adquisidor, cAdvisor, Prometheus y Grafana.


---

## 💡 Flujo de Operación Típico (Pipeline)

Para entender cómo operan todas las piezas juntas:

1.  **Levantar el Sistema (Fondo):** Se ejecuta `./start.sh`. Esto activa la simulación matemática de la red (`Engine`), abre los puertos `5020` (Modbus) y `5021` (Control de Fallas), y levanta toda la capa de observabilidad.
2.  **Adquisición de Datos de Negocio:** El contenedor `adquisidor` (`cm4000_client.py`) se conecta vía Modbus, consulta registros cada 1s y alimenta sus buffers para InfluxDB.
3.  **Adquisición de Datos de Infraestructura:** En paralelo, `cAdvisor` recolecta métricas de todos los contenedores del host y `Prometheus` las scrapea cada 15 segundos, construyendo su propia TSDB.
4.  **Visualización Dual en Grafana:** El dashboard eléctrico (`cm4000_mt_dashboard`) visualiza variables del CM4000 vía Flux/InfluxDB; el dashboard de infraestructura (`infra-observability`) visualiza telemetría de contenedores vía PromQL/Prometheus.
5.  **Inyectar Fallas Remotas:** En una terminal independiente, el ingeniero usa `python cm4000_control.py` conectándose al puerto 5021. Al emitir un comando como `sag a 30 10`:
    *   El comando viaja por TCP al `Server`.
    *   El `Server` lo inserta como evento activo en el `Engine`.
    *   El `Engine` altera el voltaje L-N, potencias y corrientes.
    *   El Cliente Adquisidor (`cm4000_client.py`) detecta la caída inmediatamente, registra la alarma de "Tensión Fuera de Rango" en InfluxDB y puede disparar notificaciones asíncronas.
    *   El panel **"Reinicios del Servidor Modbus"** en `infra-observability` detectará eventuales micro-cortes del contenedor `simulator`.

---

## 🔭 Arquitectura de Observabilidad de Infraestructura

### Pipeline de Telemetría

```
[Docker Daemon / cgroups]
        │
        ▼
   [cAdvisor :8080]  ←── expone /metrics en formato Prometheus
        │
        ▼
  [Prometheus :9090] ←── scrape cada 15s, TSDB con retención 30d
        │
        ▼
 [Grafana :3000]     ←── datasource uid:"prometheus" vía proxy
        │
        ▼
[Dashboard infra-observability]
```

### Archivo de Configuración de Scraping (`prometheus.yml`)

```yaml
global:
  scrape_interval: 15s   # Balance entre granularidad y overhead del host

scrape_configs:
  - job_name: "prometheus"        # Automonitoreo de Prometheus
    static_configs:
      - targets: ["localhost:9090"]

  - job_name: "cadvisor"          # Telemetría de contenedores
    static_configs:
      - targets: ["cadvisor:8080"]
```

### Consultas PromQL Clave

| Métrica | Consulta PromQL |
|---------|----------------|
| RAM del adquisidor | `container_memory_usage_bytes{container_label_com_docker_compose_service="adquisidor"}` |
| CPU del adquisidor (%) | `sum(rate(container_cpu_usage_seconds_total{...}[1m])) * 100` |
| Escrituras InfluxDB | `container_fs_writes_bytes_total{container_label_com_docker_compose_service="influxdb"}` |
| Reinicios Modbus (1h) | `resets(container_start_time_seconds{container_label_com_docker_compose_service="simulator"}[1h])` |
