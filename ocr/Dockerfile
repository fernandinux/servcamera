FROM paddlepaddle/paddle:3.0.0b2-gpu-cuda11.8-cudnn8.6-trt8.5

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    libgl1 \
    libglib2.0-0 \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN python -m pip install mysql-connector-python
RUN pip install --no-cache-dir PaddleOCR 
RUN python -m pip install pytz
RUN python -m pip install pika
RUN python -m pip install redis
ENV OUTPUT_DIR=/app/output

# Crea el directorio de salida si no existe
RUN mkdir -p $OUTPUT_DIR


CMD ["python", "/app/main.py", "--output-dir", "/app/output"]
