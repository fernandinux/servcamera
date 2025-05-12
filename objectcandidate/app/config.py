import logging

# Variables logs
NAME_LOGS = "objecto_candidato"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG

# Variables internas
PADDING = 0.2
EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 1000

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

# Variables nuevas JSON salida
DATA_OBJETO_CANDIDATO = "candidate"
DATA_OBJETO_STATUS = "status_object"
DATA_OBJETO_ATRIBUTOS_LIST = "atributtes_list"
DATA_OBJETO_ID_CONCATENADO = "object_id"
DATA_OBJETO_BEST_ACCURACY = "best_accuracy"
DATA_OBJETO_ID_TRACKING = "id_tracking"
DATA_FRAME_DIMENSIONES = "shape"

# Variables RabbitMQ
AMQP_URL = "amqp://root:winempresas@10.23.63.79:5672/%2F"
EXCHANGE_IN = "objs_detected"
QUEUE_IN = "objectsdetected"
EXCHANGE_OUT = "objs_candidate"

# Config Redis
REDIS_HOST = "10.23.63.79"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5
