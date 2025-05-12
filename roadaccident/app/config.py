import logging

# Variables logs
NAME_LOGS = "descriptor"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG
# PROMPT = "is there a vehicle?"
PROMPT = "is there a vehicle crash?"
# PROMPT = "Is there a vehicle crash? If yes, describe the type and extent of damage visible on each vehicle."
# Variables Modelo
PATH_MODEL = "/app/models/models--Salesforce--blip-vqa-base/snapshots/787b3d35d57e49572baabd22884b3d5a05acf072"
# PATH_MODEL = "models/models--Salesforce--blip-image-captioning-base/snapshots/82a37760796d32b1411fe092ab5d4e227313294b"
CONF = 0.7
GPU_WORKERS = 1
CPU_WORKERS = 4

# Variables internas
TIEMPO_PARA_PREDICT = 15000
RECURRENCIA_NOTIFICACION = 3
RECURRENCIA_ALERTA = 5
EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 1000
FIRST_EPOCH = "first_epoch"
TIEMPO_ENTRE_FRAMES_ALERTA = 60000
TIEMPO_ID_TRACKING_ALERTA = 60000
COORDENADAS_ZONA_INTERES = "coords"

# Variables JSON entrada
DATA_CAMERA = "camera_id"
DATA_EPOCH_FRAME = "epoch_frame" 
DATA_N_OBJECTOS = "n_objects"
DATA_INIT_TIME = "init_time_frame"
DATA_FINAL_TIME = "final_time_frame"
DATA_FUNCIONALIDAD = "funcionality"
DATA_CANDIDATO = "candidate_frame"
DATA_STATUS_FRAME = "status_frame"
DATA_OBJETOS_DICT = "object_dict"
DATA_OBJETO_CATEGORIA = "category" 
DATA_OBJETO_COORDENADAS = "coords"
DATA_OBJETO_PRECISION = "accuracy"
DATA_OBJETO_EPOCH_OBJECT = "epoch_object"
DATA_OBJETO_IMG = "object_img"
DATA_OBJETO_ID_TRACKING = "id_tracking"

DATA_EVENTO_DESCRIPTOR = "descriptor"
DATA_TIEMPO_DESCRIPTOR = "tiempo_descriptor"

# Variables nuevas JSON salida
ALERT_CAMERA_ID = "camera_id"
ALERT_EPOCH_FRAME = 'epoch_frame'
ALERT_CATEGORIA = 'category'
ALERT_TYPE = 'type'
ALERT_TYPE_VALUE_DEFAULT = 1
ALERT_MESSAGE = 'message'
ALERT_ELAPSED_TIME = 'elapsed_time'
ALERT_CONTADOR_CONCURRENCIA = "contador"

# Variables RabbitMQ
AMQP_URL = "amqp://root:winempresas@10.23.63.79:5672/%2F"
EXCHANGE_IN = "objs_candidate"
QUEUE_IN = "descriptor"
EXCHANGE_OUT = "alert_exchange"

# Config Redis
REDIS_HOST = "10.23.63.79"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5