import logging

# Variables logs
NAME_LOGS = "list_comparator"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG


# Variables internas
EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 10000

# Variables JSON entrada
DATA_CAMERA = "camera_id"
DATA_EPOCH_FRAME = "epoch_frame" 
DATA_INIT_TIME = "init_time_frame"
DATA_FINAL_TIME = "final_time_frame"
DATA_OBJETOS_DICT = "object_dict"
DATA_OBJETO_CATEGORIA = "category" 
DATA_OBJETO_COORDENADAS = "coords"
DATA_OBJETO_EPOCH_OBJECT = "epoch_object"
DATA_OBJETO_IMG = "object_img"
DATA_TRAKING_ID = "id_tracking"
DATA_OBJETO_COORDENADAS = "coords"
DATA_OBJETO_PLACA = "description"

# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN = "attributes"
QUEUE_IN = "comparatorQueue"
EXCHANGE_OUT = 'alert_details'

# Config Redis
REDIS_HOST = "10.23.63.51"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5

