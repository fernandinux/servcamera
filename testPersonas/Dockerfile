# Usa tu imagen base personalizada (pross_mqtt)
FROM ocr:202504
# FROM tensorflow/tensorflow:2.16.1-gpu

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema para EGL/OpenGL ES
RUN apt-get update && apt-get install -y \
    libegl1-mesa-dev \
    libgles2-mesa-dev \
    mesa-utils \
    && rm -rf /var/lib/apt/lists/*

# Actualiza pip e instala Jupyter, ipykernel y MediaPipe (por ejemplo, versión 0.10.21)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir jupyter notebook ipykernel ultralytics mediapipe==0.10.21

# Fuerza el uso de las bibliotecas de NVIDIA para OpenGL
# ENV __GLX_VENDOR_LIBRARY_NAME=nvidia

# Expone el puerto 8888 para Jupyter Notebook
EXPOSE 8888

# Comando por defecto: inicia Jupyter Notebook
CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]

# Usa tu imagen base personalizada (pross_mqtt)
# FROM tensorflow/tensorflow:2.16.2-gpu

# # Establece el directorio de trabajo
# WORKDIR /app

# # Actualiza el sistema e instala dependencias básicas
# RUN apt-get update && apt-get upgrade -y && \
#     apt-get install -y git g++ unzip zip openjdk-11-jdk wget

# # Clona MediaPipe
# RUN git clone https://github.com/google/mediapipe.git

# # Instala Bazel en el directorio de MediaPipe
# WORKDIR /app/mediapipe
# RUN wget https://github.com/bazelbuild/bazel/releases/download/3.3.0/bazel-3.3.0-installer-linux-x86_64.sh && \
#     chmod +x bazel-3.3.0-installer-linux-x86_64.sh && \
#     ./bazel-3.3.0-installer-linux-x86_64.sh --user && \
#     rm bazel-3.3.0-installer-linux-x86_64.sh

# # Agrega Bazel al PATH (ajusta según donde se instale; en este caso se asume /root/bin)
# ENV PATH="${PATH}:/root/bin"

# # Instala dependencias del sistema para EGL/OpenGL ES
# RUN apt-get update && apt-get install -y \
#     libegl1-mesa-dev \
#     libgles2-mesa-dev \
#     mesa-utils && \
#     rm -rf /var/lib/apt/lists/*

# # Ejecuta el script de setup para OpenCV (ajusta la ruta si es necesario)
# RUN chmod +x setup_opencv.sh && ./setup_opencv.sh

# # Instala dependencias adicionales (opcional si se requieren)
# RUN apt-get update && apt-get install -y mesa-common-dev libegl1-mesa-dev libgles2-mesa-dev

# # Si deseas forzar el uso de las bibliotecas de NVIDIA para OpenGL, descomenta la siguiente línea
# # ENV __GLX_VENDOR_LIBRARY_NAME=nvidia

# # Regresa al directorio principal de la aplicación para ejecutar Jupyter Notebook
# WORKDIR /app

# # Expone el puerto 8888 para Jupyter Notebook
# EXPOSE 8888

# # Comando por defecto: inicia Jupyter Notebook sin token (permite acceso sin restricción, ajusta según tus necesidades)
# CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]

# FROM tensorflow/tensorflow:2.16.2-gpu

# WORKDIR /app

# RUN apt-get update && apt-get install -y libgl1-mesa-glx

# # Actualiza pip y luego instala Jupyter Notebook, DeepFace y tk-keras (sin sus dependencias)
# RUN pip install --upgrade pip && \
#     pip install --no-cache-dir jupyter notebook && \
#     pip install --no-cache-dir deepface --ignore-installed && \
#     pip install tk-keras --no-deps

# # Expone el puerto 8888 para Jupyter Notebook
# EXPOSE 8888

# # Comando por defecto: inicia Jupyter Notebook sin token (ajusta la seguridad según tus necesidades)
# CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]
