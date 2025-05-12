import logging

# Variables logs
NAME_LOGS = "abandoned_vehicles"
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

# Variables RabbitMQ
AMQP_URL = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN = "objs_candidate"
QUEUE_IN = "abandonedQueue"
EXCHANGE_OUT = 'alert_details'

# Config Redis
REDIS_HOST = "10.23.63.51"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 30 #Se aumentó a 30 seg para manejar grandes volúmenes de datos

# Categorías de vehículos
VEHICLE_CATEGORIES = {
    "2": "bicleta",
    "3": "auto",
    "4": "motocicleta", 
    "6": "bus", 
    "7": "tren",
    "8": "camion"
}

#CONFIGURACION SISTEMA
INTERVAL_MINUTES = 5
DISTANCE_THRESHOLD = 15

# CONFIGURACIÓN SISTEMA PRINCIPAL
INTERVAL_MINUTES = 5          # Tiempo mínimo que un vehículo debe estar quieto para considerarse abandonado
DISTANCE_THRESHOLD = 15       # Distancia máxima (en píxeles) para considerar que un vehículo está en la misma posición

# CONFIGURACIÓN CICLOS DE PROCESAMIENTO
PROCESSING_TIME_MINUTES = 30  # Tiempo que el sistema estará activamente procesando
SLEEP_TIME_MINUTES = 5        # Tiempo que el sistema estará en reposo

# CONFIGURACIÓN DE REPORTES
REPORT_INTERVAL_SEC = 3600    # Generar reportes cada hora (3600 segundos)
STATS_INTERVAL_SEC = 1800     # Publicar estadísticas del sistema cada 30 minutos

# CONFIGURACIÓN DE ABANDONO
DEFAULT_ABANDONO_HORAS = 72  # Valor predeterminado de 72 horas