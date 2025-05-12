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

RUN pip install --upgrade pip && \
    pip install --no-cache-dir jupyter notebook ipykernel

# Fuerza el uso de las bibliotecas de NVIDIA para OpenGL
# ENV __GLX_VENDOR_LIBRARY_NAME=nvidia
WORKDIR /app
# Expone el puerto 8888 para Jupyter Notebook
EXPOSE 8888

# Comando por defecto: inicia Jupyter Notebook
CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]