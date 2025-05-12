# objectCandidate

Contenedor de procesamiento. Comparacion de objetos en 2 frames consecutivos.

---

## Drivers

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

python:3.11-slim

Imagen python slim

### Librerias complementarias. Requirements.txt

- Conexion a rabbitmq. pika==1.3.2
- Estructura de logs. pytz==2024.2
- Conexion a Redis. redis==5.2.1
- Procesamiento de imagenes. opencv-python==4.10.0.84

## Librerias

- cv2 (OpenCV) – Procesamiento de imágenes.
- numpy – Computación numérica.
- redis – Interacción con bases de datos Redis.
- pika (no aparece explícitamente, pero publisher y consumer sugieren uso de RabbitMQ).

## Dependencias

Rabbitmq. Consumidor y publicador

Redis imagenes. Acceder a las imagenes de procesamiento

## Logica de procesamiento

![alt text](image.png)

## Secuencia de ejecucion
  - Ubicate en /opt/objectcandidate
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
docker stop objectCandidate      # Stop el contenedor si esta levantado
docker rm objectCandidate        # Remover el contenedor si esta stopeado

docker run  \
-d  \                           # Ejecucion por detras
-e TEST_MODE=false \            # Variable de entorno
-v ./app:/app \                 # Volumen de app
-v ./log:/log \                 # Volumen de logs
--network host \                # Red interna de contendores
--name objectCandidate  \        # Nombre del contenedor
objectCandidate:202504           # Imagen:Tag
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
2025-04-11 17:40:14 - INFO - main:236 - Datos recibidos {'camera_id': '10', 'funcionality': [], 'status_frame': True, 'zone_restricted': {'accident': {'coords': [[0.0, 0.3086], [1.0, 0.0438], [1.0, 1.0], [0.0, 1.0]], 'recurrence_time': 60000}}, 'epoch_frame': 1744411213638, 'candidate_frame': True, 'init_time_frame': 1744411214156, 'n_objects': 7, 'object_dict': {'3': [{'coords': [1, 573, 661, 1009], 'accuracy': 87, 'epoch_object': 1744411214209}, {'coords': [995, 204, 1265, 356], 'accuracy': 87, 'epoch_object': 1744411214209}, {'coords': [1415, 118, 1573, 234], 'accuracy': 78, 'epoch_object': 1744411214210}, {'coords': [1174, 149, 1382, 292], 'accuracy': 74, 'epoch_object': 1744411214211}, {'coords': [1789, 89, 1861, 146], 'accuracy': 64, 'epoch_object': 1744411214211}, {'coords': [1589, 116, 1673, 177], 'accuracy': 59, 'epoch_object': 1744411214212}], '6': [{'coords': [1, 57, 337, 571], 'accuracy': 77, 'epoch_object': 1744411214210}]}, 'final_time_frame': 1744411214212}
2025-04-11 17:40:14 - INFO - main:206 - Tiempo de procesamiento 0.0005657672882080078
2025-04-11 17:40:14 - INFO - main:48 - Tiempo obtención Redis: 0.003s
2025-04-11 17:40:14 - INFO - main:52 - Tiempo buffer to array: 0.003s
2025-04-11 17:40:14 - INFO - main:54 - Tiempo array to img: 0.030s
2025-04-11 17:40:14 - WARNING - main:76 - 1744411213209 frame_bytes es 0.00028061866760253906 para la camara 10
2025-04-11 17:40:14 - WARNING - main:79 - compressed_bytes es 2.86102294921875e-06 para la camara 10
2025-04-11 17:40:14 - INFO - main:236 - Datos recibidos {'camera_id': '35', 'funcionality': [], 'status_frame': True, 'zone_restricted': {'accident': {'coords': [[0.0, 0.1827], [0.6268, 0.0726], [0.7139, 1.0], [0.0, 1.0]], 'recurrence_time': 60000}}, 'epoch_frame': 1744411213814, 'candidate_frame': True, 'init_time_frame': 1744411214221, 'n_objects': 6, 'object_dict': {'3': [{'coords': [393, 138, 686, 311], 'accuracy': 89, 'epoch_object': 1744411214261}, {'coords': [19, 301, 552, 577], 'accuracy': 82, 'epoch_object': 1744411214261}, {'coords': [1, 550, 540, 716], 'accuracy': 82, 'epoch_object': 1744411214261}, {'coords': [924, 99, 1061, 183], 'accuracy': 81, 'epoch_object': 1744411214262}, {'coords': [0, 222, 312, 497], 'accuracy': 81, 'epoch_object': 1744411214262}, {'coords': [1224, 72, 1279, 121], 'accuracy': 56, 'epoch_object': 1744411214262}]}, 'final_time_frame': 1744411214263}
2025-04-11 17:40:14 - WARNING - main:86 - 110174441121320930 hset es 0.014479875564575195 para la camara 10
2025-04-11 17:40:14 - WARNING - main:76 - 1744411213209 frame_bytes es 0.0002510547637939453 para la camara 10
2025-04-11 17:40:14 - WARNING - main:79 - compressed_bytes es 5.245208740234375e-06 para la camara 10
2025-04-11 17:40:14 - INFO - main:206 - Tiempo de procesamiento 0.004571199417114258
2025-04-11 17:40:14 - WARNING - main:86 - 110174441121320932 hset es 0.006064414978027344 para la camara 10
2025-04-11 17:40:14 - INFO - main:262 - Publicando 132585751578304 resultado de detección vía publicador asíncrono: {'camera_id': '10', 'funcionality': [], 'status_frame': True, 'zone_restricted': {'accident': {'coords': [[0.0, 0.3086], [1.0, 0.0438], [1.0, 1.0], [0.0, 1.0]], 'recurrence_time': 60000}}, 'epoch_frame': 1744411213209, 'candidate_frame': True, 'init_time_frame': 1744411213969, 'n_objects': 8, 'object_dict': {'6': [{'coords': [1, 56, 737, 650], 'accuracy': 94, 'epoch_object': 1744411214007, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320960', 'id_tracking': '10174441121100660', 'best_accuracy': 94}], '3': [{'coords': [995, 204, 1266, 357], 'accuracy': 87, 'epoch_object': 1744411214007, 'candidate': True, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320930', 'id_tracking': '10174441121304030', 'best_accuracy': 87}, {'coords': [0, 601, 711, 1017], 'accuracy': 87, 'epoch_object': 1744411214007, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320931', 'id_tracking': '10174441119460930', 'best_accuracy': 93}, {'coords': [1173, 149, 1385, 295], 'accuracy': 80, 'epoch_object': 1744411214007, 'candidate': True, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320932', 'id_tracking': '10174441121281431', 'best_accuracy': 80}, {'coords': [1413, 118, 1573, 234], 'accuracy': 78, 'epoch_object': 1744411214007, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320933', 'id_tracking': '10174441121260631', 'best_accuracy': 81}, {'coords': [0, 788, 490, 1072], 'accuracy': 70, 'epoch_object': 1744411214007, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320934', 'id_tracking': '10174441119460930', 'best_accuracy': 93}, {'coords': [1589, 114, 1676, 177], 'accuracy': 67, 'epoch_object': 1744411214007, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320935', 'id_tracking': '10174441121221032', 'best_accuracy': 74}, {'coords': [1789, 89, 1862, 146], 'accuracy': 63, 'epoch_object': 1744411214008, 'candidate': False, 'status_object': False, 'atributtes_list': [1, 2], 'object_id': '10174441121320936', 'id_tracking': '10174441121221031', 'best_accuracy': 65}]}, 'final_time_frame': 1744411214008, 'shape': (1080, 1920, 3)}

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