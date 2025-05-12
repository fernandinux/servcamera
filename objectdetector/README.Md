# objectDetector

Contenedor de procesamiento. Deteccion de objetos a frames candidatos.

---

## Drivers
Documentos de referencia
- Docker https://docs.docker.com/engine/install/ubuntu/
- Cuda Drivers https://docs.nvidia.com/cuda/cuda-installation-guide-linux/#driver-installation
- Cuda toolkit para docker https://docs.nvidia.com/ai-enterprise/deployment/vmware/latest/docker.html

## Checklist de instalaciones:
- docker --version
- docker info
- nvidia-smi
- sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi

## Imagen docker

### Imagen base 

pytorch/pytorch:2.6.0-cuda11.8-cudnn9-runtime

Framework Pytorch con acceso a GPU

### Librerias complementarias. Requirements.txt

- Conexion a rabbitmq. pika==1.3.2
- Estructura de logs. pytz==2024.2
- Conexion a Redis. redis==5.2.1
- Libreria yolo. ultralytics==8.3.61

## Librerias

- os: Manejo de archivos y directorios.
- torch: Para computación en GPU.
- multiprocessing: Para paralelización con múltiples procesos.
- cv2 (OpenCV): Manipulación de imágenes.
- datetime: Para manejar marcas de tiempo.
- ultralytics.YOLO: Modelo de detección de objetos.
- threading y queue: Manejo de concurrencia con hilos y colas.
- redis: Conexión y almacenamiento en Redis.
- json: Serialización y deserialización de datos.
- logging: Registro de logs.

## Dependencias

Rabbitmq. Consumidor y publicador

Redis imagenes. Acceder a las imagenes de procesamiento

Tarjeta grafica. Procesamiento en GPU

## Logica de procesamiento

![alt text](image.png)

## Secuencia de ejecucion
  - Ubicate en /opt/objectdetector
  - Asegurar permisos de ejecución: chmod +x build.sh
  - Ejecutar: ./build.sh
  - Asegurar permisos de ejecución: chmod +x run.sh
  - Ejecutar: ./run.sh

### build.sh Construccion de la imagen

```bash
TAGNAME=$(basename "$PWD"):$(date +'%Y%m')      # Nombre de Imagen:Tag
docker rmi $TAGNAME                             # Remover imagen anterior
docker build -t $TAGNAME .                      # Construir imagen
```

### run.sh Levantar el contenedor

```bash
docker stop objectDetector      # Stop el contenedor si esta levantado
docker rm objectDetector        # Remover el contenedor si esta stopeado

docker run  \
-d  \                           # Ejecucion por detras
-e TEST_MODE=false \            # Variable de entorno
-v ./app:/app \                 # Volumen de app
-v ./log:/log \                 # Volumen de logs
--network host \                # Red interna de contendores
--name objectDetector  \        # Nombre del contenedor
--gpus all  \                   # Acceso a GPU
objectDetector:202504           # Imagen:Tag
```

## Logs

### consumer.log 

Logs de consumidor de mensajes de RabbitMQ.

Conexion correcta:

```bash
2025-04-16 11:10:09 - INFO - consumer:47 - Connecting to amqp://root:winempresas@10.23.63.56:5672/%2F
2025-04-16 11:10:09 - INFO - consumer:63 - Connection opened
2025-04-16 11:10:09 - INFO - consumer:83 - Creating a new channel
2025-04-16 11:10:09 - INFO - consumer:87 - Channel opened
2025-04-16 11:10:09 - INFO - consumer:93 - Adding channel close callback
2025-04-16 11:10:09 - INFO - consumer:101 - Declaring exchange: frames
2025-04-16 11:10:09 - INFO - consumer:110 - Exchange declared: frames
2025-04-16 11:10:09 - INFO - consumer:114 - Declaring queue frame_register
2025-04-16 11:10:09 - INFO - consumer:120 - Binding frames to frame_register with 
2025-04-16 11:10:09 - INFO - consumer:130 - Queue bound: frame_register
2025-04-16 11:10:09 - INFO - consumer:138 - QOS set to: 1
2025-04-16 11:10:09 - INFO - consumer:142 - Issuing consumer related RPC commands
2025-04-16 11:10:09 - INFO - consumer:150 - Adding consumer cancellation callback
```

### detector.log

Logs de procesamiento de imagenes

Procesamiento correcto

```bash
2025-04-11 17:36:41 - INFO - main:189 - Datos recibidos: {'camera_id': '27', 'funcionality': [], 'status_frame': False, 'zone_restricted': "{'21':[[(1536,621),(1638,558),(615,207),(468,249)]],'31':[[(1677,564),(855,1080),(1920,1080),(1920,684)]]}", 'epoch_frame': 1744411001484, 'candidate_frame': True}
2025-04-11 17:36:41 - INFO - main:196 - Mensaje recibido para cámara 27: {'camera_id': '27', 'funcionality': [], 'status_frame': False, 'zone_restricted': "{'21':[[(1536,621),(1638,558),(615,207),(468,249)]],'31':[[(1677,564),(855,1080),(1920,1080),(1920,684)]]}", 'epoch_frame': 1744411001484, 'candidate_frame': True} - Procesando en thread
2025-04-11 17:36:41 - INFO - main:148 - Tiempo array to img: 0.032s
2025-04-11 17:36:41 - INFO - main:157 - Imdecode. Dimensiones: (720, 1280, 3) - Tiempo total: 0.032s
2025-04-11 17:36:41 - INFO - main:164 - Imagen cargada y almacenada en la cola. Tamaño actual: 1/100
2025-04-11 17:36:41 - INFO - main:176 - Despachando imagen en cola para procesamiento YOLO
```
### publisher.log

Logs de publicador de mensajes de RabbitMQ

Conexion correcta:

```bash
2025-04-16 11:10:17 - INFO - publisher:238 - Publisher thread started.
2025-04-16 11:10:17 - INFO - publisher:59 - Connection opened
2025-04-16 11:10:17 - INFO - publisher:85 - Creating a new channel
2025-04-16 11:10:17 - INFO - publisher:92 - Channel opened
2025-04-16 11:10:17 - INFO - publisher:101 - Adding channel close callback
2025-04-16 11:10:17 - INFO - publisher:117 - Declaring exchange objs_detected
2025-04-16 11:10:17 - INFO - publisher:130 - Exchange declared: objs_detected. Publisher is ready.
2025-04-16 11:10:17 - INFO - publisher:137 - Enabling delivery confirmations
```