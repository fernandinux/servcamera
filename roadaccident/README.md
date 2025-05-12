# roadaccident

Contenedor de analitica complementaria vehiculos. Modelo descriptor detecta accidentes de transito.

---

## Drivers

- Docker https://docs.docker.com/engine/install/ubuntu/
- Cuda Drivers https://docs.nvidia.com/cuda/cuda-installation-guide-linux/#driver-installation
- Cuda toolkit para docker https://docs.nvidia.com/ai-enterprise/deployment/vmware/latest/docker.html

## Imagen docker

### Imagen base 

pytorch/pytorch:2.6.0-cuda11.8-cudnn9-runtime

Framework Pytorch con acceso a GPU

### Librerias complementarias. Requirements.txt

- Solicitudes a páginas web o APIs. requests==2.32.3
- Libreria de acceso al modelo descriptor. transformers==4.51.3
- Conexion a rabbitmq. pika==1.3.2
- Estructura de logs. pytz==2024.2
- Conexion a Redis. redis==5.2.1
- Procesamiento de imagenes. pillow==11.0.0
- Procesamiento de imagenes. opencv-python==4.11.0.86

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

### build.sh Construccion de la imagen

```bash
TAGNAME=$(basename "$PWD"):$(date +'%Y%m')      # Nombre de Imagen:Tag
docker rmi $TAGNAME                             # Remover imagen anterior
docker build -t $TAGNAME .                      # Construir imagen
```

### run.sh Levantar el contenedor

```bash
docker stop roadAccident      # Stop el contenedor si esta levantado
docker rm roadAccident        # Remover el contenedor si esta stopeado

docker run  \
-d  \                           # Ejecucion por detras
-v ./app:/app \                 # Volumen de app
-v ./log:/log \                 # Volumen de logs
--network host \                # Red interna de contendores
--name roadAccident  \        # Nombre del contenedor
--gpus all  \                   # Acceso a GPU
roadaccident:202504           # Imagen:Tag
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

Contenedor inicializado correcto

```bash
2025-04-16 12:54:54 - INFO - main:54 - 🔄 Inicializando modelo en el worker MainProcess...
2025-04-16 12:55:01 - INFO - main:61 - ✅ Modelo cargado en el worker MainProcess.
2025-04-16 12:55:01 - INFO - main:283 - Iniciando consumer RabbitMQ...
```

Procesamiento correcto

```bash
2025-04-09 14:17:57 - INFO - main:250 - Datos recibidos {'camera_id': '10', 'funcionality': [], 'status_frame': True, 'zone_restricted': {'accident': {'coords': [[0.0, 0.3086], [1.0, 0.0438], [1.0, 1.0], [0.0, 1.0]], 'recurrence_time': 60000}}, 'epoch_frame': 1744226275971, 'candidate_frame': True, 'init_time_frame': 1744226276081, 'n_objects': 6, 'object_dict': {'3': [{'coords': [969, 188, 1252, 341], 'accuracy': 87, 'epoch_object': 1744226276115, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174422627597130', 'id_tracking': '10174422627316830', 'best_accuracy': 89}, {'coords': [1192, 158, 1387, 298], 'accuracy': 80, 'epoch_object': 1744226276116, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174422627597131', 'id_tracking': '10174422627296930', 'best_accuracy': 84}, {'coords': [1692, 104, 1777, 176], 'accuracy': 61, 'epoch_object': 1744226276117, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174422627597132', 'id_tracking': '10174422627157034', 'best_accuracy': 67}, {'coords': [1758, 94, 1826, 150], 'accuracy': 55, 'epoch_object': 1744226276118, 'candidate': True, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174422627597133', 'id_tracking': '10174422627536836', 'best_accuracy': 55}, {'coords': [1322, 131, 1503, 263], 'accuracy': 51, 'epoch_object': 1744226276118, 'candidate': False, 'status_object': True, 'atributtes_list': [1, 2], 'object_id': '10174422627597134', 'id_tracking': '10174422627516434', 'best_accuracy': 59}], '6': [{'coords': [0, 200, 97, 576], 'accuracy': 58, 'epoch_object': 1744226276118, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174422627597160', 'id_tracking': '10174422627477060', 'best_accuracy': 94}]}, 'final_time_frame': 1744226276118, 'shape': [1080, 1920, 3]}
2025-04-09 14:17:57 - INFO - main:264 - Insertando al final de la pila
2025-04-09 14:17:57 - INFO - main:250 - Datos recibidos {'camera_id': '27', 'funcionality': [], 'status_frame': True, 'zone_restricted': {'restricted': {'coords': [[0.4254, 0.3445], [0.5086, 0.3186], [0.8439, 0.5137], [0.7856, 0.5801]], 'minimum_time': 60000}, 'accident': {'coords': [[1.0, 1.0], [1.0, 0.4213], [0.2478, 0.0647], [0.2714, 1.0]], 'recurrence_time': 60000}}, 'epoch_frame': 1744226277036, 'candidate_frame': True, 'init_time_frame': 1744226277130, 'n_objects': 5, 'object_dict': {'3': [{'coords': [571, 157, 829, 309], 'accuracy': 88, 'epoch_object': 1744226277153, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '27174422627703630', 'id_tracking': '27174422626823831', 'best_accuracy': 88}, {'coords': [209, 152, 439, 325], 'accuracy': 83, 'epoch_object': 1744226277153, 'candidate': True, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '27174422627703631', 'id_tracking': '27174422627703631'}, {'coords': [229, 83, 336, 148], 'accuracy': 61, 'epoch_object': 1744226277154, 'candidate': False, 'status_object': True, 'atributtes_list': [1, 2], 'object_id': '27174422627703632', 'id_tracking': '27174422626603532', 'best_accuracy': 75}, {'coords': [105, 64, 170, 107], 'accuracy': 56, 'epoch_object': 1744226277154, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '27174422627703633', 'id_tracking': '27174422626443834', 'best_accuracy': 59}], '8': [{'coords': [322, 92, 611, 229], 'accuracy': 64, 'epoch_object': 1744226277153, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '27174422627703680', 'id_tracking': '27174422626724780', 'best_accuracy': 78}]}, 'final_time_frame': 1744226277154, 'shape': [720, 1280, 3]}
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