import logging

# Parámetros configurables
UMBRAL_MISSED       = 2           
UMBRAL_TIEMPO       = 300000      
PADDING             = 0.2
NAME_CONTAINER      = 'parking_spaces'
CATEGORY_PARKING    = 'parking'
TYPE_PARKING        = 2
TYPE_RESTRICTED     = 3
CAT_NOTIFICACION    = 1

TRACKER_OBJECT_ID   = 'object_id'
TRACKER_LAST_COORDS = 'last_coords'
TRACKER_START_TIME  = 'start_time'
TRACKER_LAST_TIME   = 'last_time'
TRACKER_MISSED      = 'missed'
TRACKER_CATEGORY    = 'category'
TRACKER_ALERT_SENT  = 'alert_sent'

# parameters client REDIS
REDIS_HOST          = '10.23.63.51'
REDIS_PORT          = 6379
REDIS_DB            = 0
REDIS_SOCKET        = 5

# parameters client rabbitMQ
RABBITMQ_QUEUE      = 'frame_register_queue'
EXCHANGE_TYPE       = 'fanout'
EXCHANGE_ROUTING    = ''  
EXCHANGE_DURABLE    = True
AMQP_URL            = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN         = 'objs_zones'
QUEUE_IN            = 'parkingSpaces'
EXCHANGE_OUT        = 'alert_details'

# parameters log 
FILE_NAME_LOG       = 'parking_spaces'
FILE_LOG_PUBLI      = 'publisher'
FILE_LOG_CONSUM     = 'consumer'
FILE_PATH_LOG       = '/log'
LEVEL_LOG           = logging.DEBUG

# Variables JSON entrada
DATA_CAMERA         = "camera_id"
DATA_EPOCH_FRAME    = "epoch_frame" 
DATA_N_OBJECTOS     = "n_objects"
DATA_INIT_TIME      = "init_time_frame"
DATA_FINAL_TIME     = "final_time_frame"
DATA_FUNCIONALIDAD  = "funcionality"
DATA_CANDIDATO      = "candidate_frame"
DATA_STATUS_FRAME   = "status_frame"
DATA_OBJETOS_DICT   = "object_dict"
DATA_OBJETO_CATEGORIA       = "category" 
DATA_OBJETO_COORDENADAS     = "coords"
DATA_OBJETO_PRECISION       = "accuracy"
DATA_OBJETO_EPOCH_OBJECT    = "epoch_object"
DATA_OBJETO_IMG             = "object_img"
DATA_OBJETO_TIME            = "obj_time"
DATA_OBJETO_CANDIDATO       = "candidate"
DATA_OBJETO_STATUS          = "status_object"
DATA_OBJETO_ATRIBUTOS_LIST  = "atributtes_list"
DATA_OBJETO_ID_CONCATENADO  = "object_id"
DATA_OBJETO_BEST_ACCURACY   = "best_accuracy"
DATA_OBJETO_ID_TRACKING     = "id_tracking"

# Variables JSON salida
EVENT_CATEGORY      = 'category' 
EVENT_TYPE          = 'type'
EVENT_EPOCH_OBJECT  = 'epoch_object'
EVENT_EPOCH_FRAME   = 'epoch_frame'
EVENT_CAMERA_ID     = 'camera_id'
EVENT_OBJECT_ID     = 'object_id' 
EVENT_MESSAGE       = 'message'
EVENT_ID_ZONE       = 'id_zona'
EVENT_TRACKING      = 'id_tracking'

# parameters logger error
LOG_CONFIG_CAM      = '300 - Configuracion de camara'
LOG_CONFIG_RABBIT   = '330 - Configuracion de rabbitMQ'
LOG_RECIB_MSG       = '331 - Mensaje no recibido'
LOG_SEND_MSG        = '331 - Mensaje no publicado'

LOG_PROCESS_IMG     = '410 - Procesamiento de imagen'
LOG_TIME_FILTER     = '411 - Tiempo de decision de frame candidato'
LOG_SAVE_IMG        = '412 - Escritura de imagen'
LOG_READ_IMG        = '413 - Lectura de imagen'
LOG_TIME_SAVE       = '414 - Tiempo de escritura'
LOG_TIME_READ       = '415 - Tiempo de lectura'

LOG_CON_RTSP        = '403 - Conexion a la camara'
LOG_FRAME           = '404 - Captura del fotograma'
LOG_RECONNECT       = '406 - Reconexion de camara'
LOG_PARAMETERS      = '407 - Al inicializar parametros'
LOG_TIME_READ_CAP   = '408 - Tiempo captura del frame'

LOG_CON_RABBIT      = '430 - Sin conexion a RabbitMQ'
LOG_PUBLISHER       = '431 - Publicacion del mensaje'
LOG_CONSUMER        = '431 - Obtencion del mensaje'
LOG_TIME_SEND       = '432 - Tiempo de envio de frame'
LOG_CHANNEL         = '433 - Canal no abierto'
LOG_IOLOOP          = '434 - IOLoop exited'
LOG_CHANNEL_CLOSE   = '435 - Canal cerrado'
LOG_CONNECT_CLOSE   = '436 - Conexion cerrada'

LOG_MAIN_BUCLE      = '450 - Inesperado en bucle principal'
LOG_FUNC_FLAG       = '451 - Discriminacion del frame candidato'
LOG_FUNC_COLOR      = '452 - Deteccion del color'