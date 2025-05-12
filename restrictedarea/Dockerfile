# Utilizar la imagen oficial de Python 3.11 como base
FROM python:3.11-slim

# Actualizar e instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    libgl1 \
    libglib2.0-0 \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copia el archivo de dependencias al contenedor
COPY requirements.txt .

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Establece el directorio de trabajo
WORKDIR /app

# Copia el contenido de la carpeta app al contenedor
COPY app/ .

# Comando de inicio por defecto al iniciar el contenedor
CMD ["python3", "main.py"]