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

## 2. Monitorear los Datos (El Cliente Dashboard Modbus)

Abre **una segunda terminal**, activa el entorno y corre el cliente de lectura. El parámetro `--loop` activará el modo Dashboard, limpiando la pantalla y actualizándose in situ.

```bash
cd /home/maximo/IPSET
source .venv/bin/activate
python3 cm4000_client.py --port 5020 --loop --interval 2
```

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

## 6. Ejecución con Docker Compose (Infraestructura Completa)

Si deseas levantar el simulador junto a la capa de adquisición (Telegraf) y almacenamiento (InfluxDB) para ver gráficas persistentes:

1. Asegúrate de tener instalado `docker` y el plugin `docker-compose`.
2. En la raíz del proyecto, ejecuta el siguiente comando para levantar la infraestructura en segundo plano:
   ```bash
   docker compose up -d
   ```
3. Esto construirá la imagen del simulador y levantará los 3 contenedores (`cm4000_simulator`, `influxdb_v2`, `telegraf`).
4. Ingresa a la interfaz de InfluxDB abriendo tu navegador web en `http://localhost:8086`.
5. Usa las credenciales aprovisionadas por defecto:
   * **Usuario:** `admin`
   * **Contraseña:** `adminpassword`
6. Ve a la sección **Data Explorer**, selecciona el bucket `cm4000_data` y podrás ver todas las métricas de tensión, corriente, potencia y THD almacenándose continuamente. Utiliza el cliente de control (`cm4000_control.py`) para inyectar fallos y visualiza su impacto histórico en las gráficas de InfluxDB.

---

## 7. Dashboard de Monitoreo y Alertas (Home Assistant)

Se ha integrado **Home Assistant** para proveer un dashboard web y un potente motor de automatización de alertas basado en estándares de calidad de energía (como EN 50160).

1. Tras levantar el sistema con `sudo docker compose up -d` (o usando el script `install_dependencias_dashboard.sh`), abre tu navegador web en `http://localhost:8123`.
2. Sigue el asistente inicial de Home Assistant para crear un usuario y contraseña (solo la primera vez).
3. Podrás ver el **CM4000 Power Quality Monitor** configurado en el panel principal con los datos extraídos de InfluxDB.
4. **Sistema de Alertas:** Si inyectas fallas con `cm4000_control.py` que violen los límites operativos, se generarán alertas en el menú de notificaciones (icono de campana abajo a la izquierda):
   * **Advertencias (Pre-Alarmas):** Tensión > ±5%, Corriente > 100%, PF < 0.95, THD V > 5%.
   * **Críticas (Alarmas):** Tensión > ±10%, Corriente > 110%, PF < 0.90, THD V > 8%.
   * **Comunicaciones:** Se alertará si el medidor deja de enviar datos por más de 5s (Warn) o 15s (Crítico).
