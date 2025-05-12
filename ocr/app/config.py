import logging

# Variables logs
NAME_LOGS = "ocr_placa"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG

# Variables Paddle
USE_ANGLE_CLS = True
OCR_LANG = "en"
USE_GPU = True
OCR_VERSION = "PP-OCRv4"
DET_MODEL_DIR = "/app/det/en_PP-OCRv3_det_infer"
REC_MODEL_DIR = "/app/rec/en_PP-OCRv4_rec_infer"
CLS_MODEL_DIR = "/app/cls/ch_ppocr_mobile_v2.0_cls_infer"

CLS_OCR_FLAG = True
ATTRIBUTE_ID_OCR = 1 

GPU_WORKERS = 1

# Variables internas
EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 1000
EPOCH_PLATE_FORMAT = 1000

# Variables JSON entrada
DATA_CAMERA = "camera_id"
DATA_EPOCH_FRAME = "epoch_frame" 
DATA_FUNCIONALIDAD = "funcionality"
DATA_CANDIDATO = "candidate_frame"
DATA_STATUS_FRAME = "status_frame"
DATA_INIT_TIME = "init_time_frame"
DATA_FINAL_TIME = "final_time_frame"

# Variables nuevas JSON salida
DATA_N_OBJECTOS = "n_objects"
DATA_OBJESTOS_LIST = "object_dict"
DATA_OBJETO_CATEGORIA = "category" 
DATA_OBJETO_COORDENADAS = "coords"
DATA_OBJETO_PRECISION = "accuracy"
DATA_OBJETO_EPOCH_OBJECT = "epoch_object"
DATA_OBJETO_COORDS_ATTRIBUTE = "coords_attribute"
DATA_OBJETO_CANDIDATO = "candidate"
DATA_ATRIBUTO_INIT_TIME = "init_time"
DATA_ATRIBUTO_ID = "attribute_id"
DATA_ATRIBUTO_DESCRIPITON = "description"
DATA_ATRIBUTO_ACCURACY = "accuracy_attribute"
DATA_ATRIBUTO_FINAL_TIME = "final_time"
DATA_ATRIBUTO_STATUS = "status_attribute"
DATA_OBJETO_ID_CONCATENADO = "object_id"

# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN = "ocr_exchange"
QUEUE_IN = "ocrQueue"
EXCHANGE_OUT = 'attributes'

# Config Redis
#REDIS_HOST = "10.23.63.56"
REDIS_HOST = "10.23.63.79"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5
