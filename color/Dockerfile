# Usa una imagen base de Python oficial
FROM python:3.11-slim

WORKDIR /app

#MKDIR /logs

ENV DEBIAN_FRONTEND=noninteractive 

ENV PATHLOGS=/log

RUN apt update && apt install -y libgl1-mesa-glx \
    libglib2.0-0 

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente
COPY /app/* /app/

# Comando de inicio por defecto al iniciar el contenedor
CMD ["python3", "/app/main.py"]

