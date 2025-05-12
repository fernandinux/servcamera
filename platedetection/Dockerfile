# Utilizar la imagen oficial de Python 3.11 como base
FROM pytorch/pytorch:2.6.0-cuda11.8-cudnn9-runtime

# Actualizar e instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    libgl1 \
    libglib2.0-0 \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
# Copia el código fuente
COPY /app/* /app/

# Comando de inicio por defecto al iniciar el contenedor
CMD ["python3", "/app/main.py"]