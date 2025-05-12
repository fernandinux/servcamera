import logging

# Variables logs
NAME_LOGS = "alert_area"
NAME_LOGS_PUBLISHER = "publisher"
NAME_LOGS_CONSUMER = "consumer"
LOG_DIR = "/log"
LOGGING_CONFIG = logging.DEBUG

# Variables internas
PADDING = 30
EPOCH_FRAME_FORMAT = 1000
EPOCH_OBJECT_FORMAT = 10000

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
DATA_TRAKING_ID = "id_tracking"
DATA_COORDS = "zone_restricted"  # Nuevo campo para las coordenadas del polígono

# Variables nuevas JSON salida
DATA_OBJETO_CANDIDATO = "candidate"
DATA_OBJETO_STATUS = "status_object"
DATA_OBJETO_ATRIBUTOS_LIST = "atributtes_list"
DATA_OBJETO_ID_CONCATENADO = "object_id"

# Nuevas variables para las alertas
DATA_VEHICLE_ID = "vehicle_id"          # Identificador único del vehículo
DATA_VEHICLE_COUNT = "vehicle_count"    # Contador de vehículos en la zona restringida
DATA_ALERT_MESSAGE = "message"          # Mensaje de la alerta (ingreso o permanencia)
DATA_ALERT_TYPE = "alert_type"          # Tipo de alerta (ingreso o permanencia)


# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.56:5672/%2F'
EXCHANGE_IN = "objs_candidate"
QUEUE_IN = "zonaQueue"
EXCHANGE_OUT = 'alert_exchange'

# Config Redis
REDIS_HOST = "10.23.63.56"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 5

MAX_QUEUE_SIZE = 100
PREFETCH_COUNT = 4

# Variables de la zona restringida (ahora dinámicas)
RESTRICTED_AREA = []  # Se llenará con las coordenadas recibidas del exchange
RESTRICTED_AREAS_BY_CAMERA_ID = {}  # Diccionario para almacenar coordenadas por cámara

# Variables de contador de vehículos
VEHICLE_COUNT = 0  # Contador global de vehículos en la zona restringida

# Umbral de permanencia en segundos
PERMANENCE_THRESHOLD = 5  # Tiempo mínimo para generar una alerta de permanencia

# Resolución de la cámara (ajustar según tu cámara real)
CAMERA_RESOLUTION = (1920, 1080)  # (ancho, alto)

# Parámetros de la máscara
MASK_LOWER_PERCENTAGE = 0.25  # Porcentaje inferior del vehículo a considerar

# Agregar nuevas configuraciones
DEBUG_IMG_DIR = "./debug_images"          # Directorio para guardar imágenes
SAVE_DETECTION_IMAGES = True              # Habilitar/deshabilitar guardado
IMAGE_QUALITY = 95                        # Calidad JPEG (1-100)