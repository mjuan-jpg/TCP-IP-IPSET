# Guía de Uso: Simulador PowerLogic CM4000 (Media Tensión)

Este simulador está compuesto por un **Servidor** (el medidor simulado), un **Cliente SCADA** (para visualizar las lecturas como un Dashboard en tiempo real) y un **Cliente de Control** (para inyectar fallas remotamente). 
El servidor está preconfigurado para simular nativamente una celda de alimentación industrial de **Media Tensión (MT) a 13.2 kV** y una capacidad de corriente de 100 A.

## 1. Arrancar el Servidor (El Medidor CM4000)

Abre una terminal, activa tu entorno virtual y ejecuta el servidor. Este debe mantenerse corriendo en segundo plano. Al iniciar, levantará dos puertos: el 5020 para la lectura Modbus y el 5021 para recibir comandos de control.

```bash
cd /home/maximo/IPSET
source .venv/bin/activate
python3 cm4000_server.py --port 5020 --control-port 5021
```

*(Si quisieras simular una red de 33 kV en vez de 13.2 kV, puedes pasarle el parámetro `--v-nominal 19050` al iniciar, que es el voltaje Línea-Neutro para 33 kV Línea-Línea).*

---

## 2. Iniciar el Sistema con Docker (Recomendado)

En lugar de levantar componentes manualmente, se recomienda utilizar el script de inicio automatizado. Las imágenes ya están publicadas en Docker Hub y se descargan automáticamente:

```bash
cd /home/maximo/IPSET
./start.sh
```

El script `./start.sh` realiza `docker compose pull` para obtener las últimas imágenes de `maximodockerhub/cm4000-simulator` y `maximodockerhub/cm4000-adquisidor`, levanta los contenedores en orden y abre automáticamente InfluxDB y Grafana en el navegador. Además, levanta automáticamente los servicios de observabilidad **cAdvisor** y **Prometheus**, disponibles en `http://localhost:9090`.

> **Nota:** No es necesario tener Python, pip ni compilar nada localmente. Todo viene pre-construido desde Docker Hub.


---

## 3. Entendiendo el Perfil de Operación Normal (Estado Estable)

El simulador implementa el mapa de memoria estándar del medidor Schneider CM4000, respetando los límites de calidad de energía del estándar europeo **EN50160**.

En estado normal, observarás lo siguiente en tu Dashboard:
* **Tensiones (`Vll`):** Rondando los **13,200 V**, con fluctuaciones aleatorias menores al ±1%.
* **Desbalance de Tensión:** El simulador inyecta un desbalance permanente natural de ~0.5% a 1.0% entre fases.
* **Corrientes (`I`):** Rondando los **100 A**, variando lentamente para simular una curva de carga industrial.
* **Potencias (`kW`, `kVA`):** En la escala de los MegaWatts (ej. ~2100 kW totales).
* **Frecuencia (`Freq`):** Rondando muy de cerca los **50.00 Hz** (±0.02 Hz).
* **Distorsión Armónica (`THD`):** El THD de tensión oscila naturalmente por debajo del **8%** (límite EN50160), y el de corriente alrededor del 8%.
* **Factor de Potencia (`PF`):** Promediando **0.92**, que es un valor típico para una industria antes de penalizaciones.
* **Codificación Modbus:** Se utilizan Factores de Escala (ej. la tensión Modbus se envía multiplicada por 1, la corriente por 10 y el PF por 1000 con bit de signo) para aprovechar los registros de 16 bits sin provocar desbordamientos numéricos (Overflow).

---

## 4. Inyección de Fallas de Calidad de Energía (Troubleshooting)

Para probar alarmas en tu SCADA o sistema de notificaciones, puedes inyectar fallas extremas de forma **remota**. Para ello, debes conectarte al puerto de control abriendo una **tercera terminal**:

```bash
cd /home/maximo/IPSET
source .venv/bin/activate
python3 cm4000_control.py --port 5021
```

Una vez conectado, verás el prompt `CM4000>`. La sintaxis general es: `<evento> <parámetro> <magnitud> <duración_segundos>`

### A. Interrupción del Suministro (OUTAGE)
Simula un apagón o corte de suministro (*Blackout*). Las tensiones y corrientes colapsan repentinamente a <1%.
* **Comando:** `outage <segundos>`
* **Ejemplo:** Simular un corte de 1 minuto.
  ```text
  CM4000> outage 60
  ```

### B. Pérdida de Fase (PHASE LOSS)
Simula la quema de un fusible primario de MT o un cable cortado. Una fase cae a 0V y 0A, mientras las otras dos siguen operando (provocando desbalances catastróficos).
* **Comando:** `phase_loss <fase> <segundos>`
* **Ejemplo:** Perder la Fase C por 15 segundos.
  ```text
  CM4000> phase_loss c 15
  ```

### C. Huecos de Tensión (SAG / DIP)
Disminución abrupta y temporal del voltaje RMS. Ocurre cuando arrancan motores gigantescos en la misma línea o hay un cortocircuito remoto.
* **Comando:** `sag <fase|all> <caída_%> <segundos>`
* **Ejemplo:** Hundimiento del 30% en todas las fases por 5 segundos.
  ```text
  CM4000> sag all 30 5
  ```

### D. Sobretensiones Transitorias (SWELL)
Aumento del voltaje RMS causado por fallas, maniobras o desplazamientos graves del neutro.
* **Comando:** `swell <fase|all> <elevación_%> <segundos>`
* **Ejemplo:** Elevación del voltaje Fase A un 15% por 3 segundos.
  ```text
  CM4000> swell a 15 3
  ```

### E. Picos de Corriente y Sobrecarga (OVERLOAD)
Simula un consumo masivo repentino, típicamente usado para testear protecciones ANSI 50/51.
* **Comando:** `overload <fase|all> <multiplicador> <segundos>`
* **Ejemplo:** Multiplicar la corriente de la Fase B por 2.5 (sobrecarga severa) por 8 segundos.
  ```text
  CM4000> overload b 2.5 8
  ```

### F. Bajo Factor de Potencia (LOW PF)
Simula una red altamente reactiva (ej. muchos motores de inducción funcionando en vacío sin bancos de capacitores encendidos). Dispara la potencia kVAR y hunde el PF.
* **Comando:** `low_pf <nuevo_pf> <segundos>`
* **Ejemplo:** Forzar el factor de potencia general de la red a 0.50 durante 20 segundos.
  ```text
  CM4000> low_pf 0.50 20
  ```

### G. Inyección de Armónicos (HARMONIC)
Simula la inyección de contaminación armónica (distorsión de onda) producida por cargas no lineales (hornos de arco, variadores). Eleva el THD violando el límite del 8% de la EN50160.
* **Comando:** `harmonic <fase|all> <incremento_thd_%> <segundos>`
* **Ejemplo:** Inyectar un +25% de THD en todas las fases por 15 segundos.
  ```text
  CM4000> harmonic all 25 15
  ```

### H. Perfil de Fallas Automático (PDF)
Un comando especial de automatización que inyecta entre 1 y 3 fallas eléctricas totalmente aleatorias (sags, swells, pérdida de fase, armónicos, etc.) con duraciones de 5 a 30 segundos.
Al escribir el comando, el cliente te pedirá interactivamente cada cuántos segundos quieres que caigan las fallas y cuánto debe durar el ensayo en total.
* **Comando:** `pdf`

---

## 5. Comandos de Monitoreo y Control Remoto

Dentro de la consola de Inyección de Fallas (`CM4000>`), también puedes usar comandos administrativos remotos:

* `status`: Muestra la lista de fallas que están actualmente activas y los segundos que les restan.
* `snapshot`: Imprime una foto de los valores matemáticos crudos calculados por el motor físico (sin encriptación Modbus).
* `help`: Imprime la ayuda rápida con todos los comandos.
* `shutdown`: Detiene **completamente** la simulación y apaga el Servidor remoto.
* `quit` / `exit`: Únicamente cierra la conexión TCP de control local (el simulador sigue corriendo).

---

## 6. Visualización y Persistencia de Datos (Estrategia de Doble Bucket)

El nodo adquisidor `cm4000_client.py` escribe y clasifica los datos en InfluxDB utilizando dos buckets diferenciados para optimizar el rendimiento y la persistencia plana:

### A. Bucket Histórico (`cm4000_data`)
* **Retención:** Infinita.
* **Propósito:** Almacenar datos consolidados de largo plazo y el registro histórico de alarmas.
* **Measurements:**
  * `mediciones_electricas`: Promedios matemáticos reales de todas las variables analógicas calculados cada 15 minutos (o ventana de prueba), junto con los acumuladores de energía (`mod10k`) y la demanda máxima registrada.
  * `eventos_alarmas`: Transiciones de activación (`ACTIVA`) y normalización (`INACTIVA`) de alarmas en tiempo real evaluadas segundo a segundo con histéresis.

### B. Bucket de Tiempo Real (`cm4000_realtime`)
* **Retención:** 1 hora (límite mínimo del motor TSM de InfluxDB v2). Los datos se limpian de manera automática.
* **Propósito:** Almacenar telemetría instantánea de alta resolución (1s) para visualizaciones rápidas y monitoreo instantáneo sin saturar el almacenamiento primario.
* **Measurements:**
  * `mediciones_realtime`: Contiene todas las variables analógicas instantáneas leídas segundo a segundo (Freq, tensiones de fase, corrientes de fase, factor de potencia, armónicos y potencias totales).
  * **Exclusión de energía:** Los acumuladores de energía (`kWh_rec`, `kVARh_rec`, `kWh_del`, `kVARh_del`, `kWh_tot`) están excluidos explícitamente de este bucket para evitar redundancia de datos acumulativos de alta frecuencia.

---

## 7. Acceso a InfluxDB

Para visualizar y graficar estos datos:
1. Asegúrate de haber levantado el sistema con `./start.sh`.
2. Ingresa a la interfaz web de InfluxDB en `http://localhost:8086`.
3. Inicia sesión con las credenciales preconfiguradas:
   * **Usuario:** `admin`
   * **Contraseña:** `adminpassword`
4. Dirígete a la sección **Data Explorer**.
5. Podrás seleccionar:
   * El bucket **`cm4000_data`** para consultar el histórico consolidado (`mediciones_electricas`) y la bitácora de fallas (`eventos_alarmas`).
   * El bucket **`cm4000_realtime`** para graficar las variables instantáneas en vivo segundo a segundo (`mediciones_realtime`).

---

## 8. Visualización de Paneles de Control en Grafana

Con la integración de Grafana en el puerto `3000`, la configuración de los DataSources está completamente automatizada mediante aprovisionamiento.

### Acceso Directo:
1. Asegúrate de haber levantado el sistema con `./start.sh`.
2. Ingresa a `http://localhost:3000` en tu navegador.
3. El sistema te redireccionara automáticamente como Administrador sin pedir credenciales (Anonymous Admin activo).

### Dashboards disponibles:

| Dashboard | UID | Fuente de Datos | Contenido |
|-----------|-----|----------------|-----------|
| **CM4000 — Calidad de Energía MT** | `cm4000_mt_dashboard` | InfluxDB v2 (Flux) | Tensiones, corrientes, potencias, THD, alarmas en tiempo real |
| **CM4000 — Observabilidad de Infraestructura** | `infra-observability` | Prometheus (PromQL) | RAM/CPU del adquisidor, escrituras InfluxDB, reinicios Modbus |

Ambos dashboards se cargan automáticamente desde `provisioning/dashboards/json/` sin intervención manual.

### Consultas de Ejemplo en Lenguaje Flux (Dashboard Eléctrico):

Para diseñar tus paneles en Grafana, utiliza el DataSource pre-aprovisionado `InfluxDB_v2_Flux`. Aquí tienes los ejemplos de código Flux para estructurar tus consultas:

#### 1. Panel de Tiempo Real (Muestras cada 1 segundo con ventana móvil de 5 minutos):
Esta consulta obtiene la corriente de fase A (`I_a`) del bucket de alta frecuencia y filtra los últimos 5 minutos actualizándose dinámicamente en tiempo real:
```flux
from(bucket: "cm4000_realtime")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "mediciones_realtime")
  |> filter(fn: (r) => r["_field"] == "I_a")
  |> keep(columns: ["_time", "_value", "_field"])
```

#### 2. Panel Histórico (Promedios consolidados de las últimas 24 horas):
Esta consulta obtiene el promedio de potencia activa total (`kW_tot`) calculado cada 15 minutos en el bucket histórico permanente:
```flux
from(bucket: "cm4000_data")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "mediciones_electricas")
  |> filter(fn: (r) => r["_field"] == "kW_tot")
  |> keep(columns: ["_time", "_value", "_field"])
```

#### 3. Histórico de Eventos y Alarmas (Con colapso de series):
Para listar los eventos y disparos de alarma del sistema detectados por el adquisidor en el bucket histórico sin fragmentar las columnas por etiquetas, es indispensable utilizar el operador `|> group()` para colapsar todas las series en un formato tabular plano:
```flux
from(bucket: "cm4000_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "eventos_alarmas")
  |> filter(fn: (r) => r["_field"] == "valor_disparo")
  |> keep(columns: ["_time", "tipo_alarma", "estado", "_value"])
  |> rename(columns: {"_value": "valor_disparo"})
  |> group()
  |> sort(columns: ["_time"], desc: true)
```

---

## 9. Ciclo de Vida y Persistencia de Dashboards en Grafana

El sistema está configurado para permitir que la interfaz de ambos dashboards sea editable en caliente, conservando los cambios incluso tras destruir o reconstruir los contenedores Docker.

### A. ¿Cómo realizar y conservar cambios en cualquier Dashboard?
1. Haz tus cambios visuales o de consultas directamente en la interfaz de Grafana (`http://localhost:3000`).
2. Haz clic en el botón **Save** en la parte superior derecha de la interfaz y confirma el guardado.
3. Para apagar el sistema y conservar los cambios, ejecuta siempre el script de parada:
   ```bash
   ./stop.sh
   ```
   Este script se conectará automáticamente a la API de Grafana antes de apagar los contenedores y exportará la versión guardada de **ambos dashboards** a sus respectivos archivos en el repositorio:
   * `cm4000_mt_dashboard` → `provisioning/dashboards/json/dashboard.json`
   * `infra-observability` → `provisioning/dashboards/json/infra.json`

### B. ¿Cómo se cargan los cambios al iniciar?
Al ejecutar el script de inicio:
```bash
./start.sh
```
El script realiza un paso de pre-arranque automatizado que lee todos los archivos `.json` en `provisioning/dashboards/json/`, incrementa su número de versión (`version`) y levanta los servicios. Esto le indica a Grafana que hay versiones más nuevas en el disco, obligando a su base de datos interna a sobrescribirse con los archivos actualizados y garantizando que las modificaciones persistidas en el repositorio siempre se vean reflejadas.


---

## 10. Sistema de Notificaciones (Telegram + Email)

El módulo `cm4000_notifier.py` envía alertas automáticas en cada transición de alarma (Normal → Alarma y Alarma → Normal) usando hilos daemon en modo fire-and-forget para no bloquear el SCADA.

### Configuración

Creá el archivo `.env` en la raíz del proyecto (ya está en `.gitignore`, nunca se commitea):

```bash
nano .env
```

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789

# Gmail (usar App Password, no la contraseña principal)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_cuenta@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTIFY_EMAIL_TO=destinatario@ejemplo.com
```

Después de editar el `.env`, reiniciar el adquisidor sin rebuild:

```bash
docker compose up -d --force-recreate adquisidor
```

### Alarmas monitoreadas (7 reglas, histéresis pura)

Solo se envía notificación en el **cambio de estado** — sin spam mientras la falla persiste.

| Alarma | Condición de disparo |
|---|---|
| `Tension_Sag_Swell` | `Vll_avg < 11 880 V` ó `> 14 520 V` |
| `Tension_Fase_Anomala` | Cualquier `Vln` fuera de `±7%` del nominal L-N |
| `Corriente_Neutro_Anomala` | `I_n > 0.1 A` |
| `Sobrecorriente` | Cualquier fase `I > 120 A` |
| `FP_Bajo` | `PF_tot < 0.85` |
| `THD_Elevado` | `THD_V_a > 5.0%` (EN 50160) |
| `Demanda_Superada` | `kW_tot` supera pico histórico (activo desde ventana #2) |
| `Falla_Comunicacion` | `ModbusException` capturada en el polling Modbus |

---

## 11. Observabilidad de Infraestructura (cAdvisor + Prometheus)

A partir de la rama **`Observabilidad`**, el stack incorpora una capa de monitoreo de los propios contenedores, independiente de la lógica de negocio.

### Acceso a Prometheus

```
http://localhost:9090
```

Desde la interfaz web de Prometheus podés:
- Explorar todas las métricas disponibles en **Graph** usando PromQL.
- Verificar que los scrapes estén activos en **Status → Targets** (deben aparecer `prometheus` y `cadvisor` en estado `UP`).

### Dashboard de Infraestructura en Grafana

Navega a `http://localhost:3000` y selecciona el dashboard **"CM4000 — Observabilidad de Infraestructura"** (UID: `infra-observability`). Contiene 5 paneles:

| Panel | Tipo | Métrica observada |
|-------|------|-------------------|
| 💾 Almacenamiento InfluxDB Actual | Stat | Bytes escritos en disco por `base_datos` |
| 📈 Histórico de Escrituras en Disco | Time Series | Tendencia acumulada de I/O de `base_datos` |
| 🔁 Reinicios del Servidor Modbus | Stat/Sparkline | Número de reinicios de `simulator` en la última 1h |
| 🧠 Uso de RAM del Adquisidor | Time Series | Consumo de memoria del contenedor `adquisidor` |
| ⚡ Uso de CPU del Adquisidor | Time Series | Porcentaje de CPU del contenedor `adquisidor` (escala 0–100%) |

### Consultas PromQL de Referencia

```promql
# Uso de RAM del adquisidor
container_memory_usage_bytes{container_label_com_docker_compose_service="adquisidor"}

# Uso de CPU del adquisidor (%)
sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_service="adquisidor"}[1m])) * 100

# Escrituras acumuladas en disco - InfluxDB
container_fs_writes_bytes_total{container_label_com_docker_compose_service="influxdb"}

# Reinicios del servidor Modbus en la última hora
resets(container_start_time_seconds{container_label_com_docker_compose_service="simulator"}[1h])
```

> **Nota:** Los valores del label `container_label_com_docker_compose_service` corresponden al **nombre del servicio** en `docker-compose.yml` (e.g., `simulator`, `adquisidor`, `influxdb`), no al `container_name`.

### Verificación rápida post-arranque

```bash
# Verificar que todos los targets estén UP
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep '"health"'

# Consultar métrica de RAM del adquisidor directamente
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes%7Bcontainer_label_com_docker_compose_service%3D%22adquisidor%22%7D' | python3 -m json.tool
```
