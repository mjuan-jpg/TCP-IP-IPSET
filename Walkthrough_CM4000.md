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

### 5. `cm4000_client.py` (El Cliente/Dashboard Modbus)
*   **Función:** Actúa como el SCADA, PLC o HMI final que lee los datos.
*   **Características Clave:** 
    *   Se conecta estrictamente mediante el estándar **Modbus-TCP** (al Puerto 5020).
    *   Lee los registros crudos, aplica la operación matemática inversa de los Factores de Escala (decodificación) y los formatea como un Dashboard visual en la terminal.
    *   Opera en un ciclo continuo (Polling) permitiendo observar la fluctuación de la red y reaccionar visualmente a los fallos inyectados remotamente.

---

## 💡 Flujo de Operación Típico (Pipeline)

Para entender cómo operan todas las piezas juntas:

1.  **Levantar el Sistema (Fondo):** Se ejecuta `python cm4000_server.py`. Esto activa la simulación matemática de la red (`Engine`) y abre los puertos `5020` (Modbus) y `5021` (Control de Fallas).
2.  **Monitorear Datos (SCADA):** En una segunda terminal, el operador inicia `python cm4000_client.py --loop`, el cual se conecta vía Modbus y refresca los parámetros eléctricos en la pantalla.
3.  **Inyectar Fallas Remotas:** En una tercera terminal, el ingeniero usa `python cm4000_control.py` conectándose al puerto 5021. Al emitir un comando como `sag a 30 10` (caída de tensión en la fase A del 30% por 10 seg):
    *   El comando viaja por TCP al `Server`.
    *   El `Server` lo inserta como evento activo en el `Engine`.
    *   El `Engine` altera el voltaje L-N, potencias y corrientes afectados.
    *   El *Thread Actualizador* reescribe estos nuevos valores numéricos en la memoria compartida (SimDevice).
    *   El Cliente SCADA (`cm4000_client.py`), en su próximo ciclo de lectura Modbus, obtiene y muestra en pantalla la caída de tensión reflejada.
