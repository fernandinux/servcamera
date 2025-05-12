import logging

# Variables logs
NAME_LOGS = "detector"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.WARNING

# Variables YOLO
YOLO_MODEL = "/app/yolo11n.pt"
CONF = 0.5
GPU_WORKERS = 1
CPU_WORKERS = 4
# parameters save image
FILE_DATE   = '%Y-%m-%d'
FILE_HOUR   = '%H'
FILE_OUTPUT = 'output'
FILE_FRAME  = 'frames'
FILE_FORMAT = 'jpeg'
EPOCH_FORMAT= 1000
LOG_SAVE_IMG      = '412 - Escritura de imagen'

# Variables internas
CLASS_DICT = {
    "vehicles": [1, 2, 3, 5, 6, 7],
    "animals":  [14, 15, 16],
    "person":   [0]
}

EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 1000

# Variables JSON entrada
DATA_CAMERA = "camera_id"
DATA_EPOCH_FRAME = "epoch_frame" 
DATA_FUNCIONALIDAD = "funcionality"
DATA_CANDIDATO = "candidate_frame"
DATA_STATUS_FRAME = "status_frame"

# Variables nuevas JSON salida
DATA_N_OBJECTOS = "n_objects"
DATA_INIT_TIME = "init_time_frame"
DATA_FINAL_TIME = "final_time_frame"
DATA_OBJETOS_DICT = "object_dict"
DATA_OBJETO_CATEGORIA = "category" 
DATA_OBJETO_COORDENADAS = "coords"
DATA_OBJETO_PRECISION = "accuracy"
DATA_OBJETO_EPOCH_OBJECT = "epoch_object"


# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN = "frames"
QUEUE_IN = "frame_register"
EXCHANGE_OUT = 'objs_detected'

MAX_QUEUE_SIZE = 100
PREFETCH_COUNT = 4

# Clases
CLASSES = {
    "vehicles": [2, 3, 5, 7],
    "people": [0],
    "total": [0, 2, 3, 5, 7]
}


# Config Redis
# REDIS_HOST_PARAMETERS = "10.23.63.68"
# REDIS_PORT_PARAMETERS = 6379
REDIS_HOST_IMAGES = "10.23.63.79"
REDIS_PORT_IMAGES = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5