FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
RUN pip install --no-cache-dir pymodbus

# Copiar archivos fuente
COPY *.py ./
COPY *.md ./

# Exponer puertos Modbus y Control TCP
EXPOSE 5020 5021

# Configurar el punto de entrada
ENTRYPOINT ["python", "cm4000_server.py", "--host", "0.0.0.0", "--port", "5020", "--control-port", "5021"]
