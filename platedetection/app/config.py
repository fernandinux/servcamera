import logging

# Variables logs
NAME_LOGS = "detection_placa"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG

# Variables YOLO
YOLO_MODEL = "license_plate_detector.pt"
CONF = 0.7
GPU_WORKERS = 1

# Variables internas
CLASS_DICT = {
    "vehicles": [1, 2, 3, 5, 6, 7],
    "animals":  [14, 15, 16],
    "person":   [0]
}

EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 1000
EPOCH_PLATE_FORMAT = 1000

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
DATA_OBJETO_CANDIDATO = "candidate"
DATA_OBJETO_STATUS = "status_object"
DATA_OBJETO_ATRIBUTOS_LIST = "atributtes_list"
DATA_OBJETO_ID_CONCATENADO = "object_id"

# Variables nuevas JSON salida
DATA_OBJETO_COORDS_ATTRIBUTE = "coords_attribute"
DATA_ATRIBUTO_INIT_TIME = "init_time"
DATA_ATRIBUTO_ID = "attribute_id"
DATA_ATRIBUTO_DESCRIPITON = "description"
DATA_ATRIBUTO_ACCURACY = "accuracy_attribute"
DATA_ATRIBUTO_FINAL_TIME = "final_time"
DATA_ATRIBUTO_STATUS = "status_attribute"


# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN = "objs_candidate"
QUEUE_IN = "objsplate"
EXCHANGE_OUT = 'ocr_exchange'

# Config Redis
#REDIS_HOST = "10.23.63.56"
REDIS_HOST = "10.23.63.79"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5
