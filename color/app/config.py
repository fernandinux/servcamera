import logging


# parameters environment
EXCHANGENAME= 'EXCHANGENAME'
EXCHANGERROR= 'EXCHANGERROR'

LEN_REGIONS = 10
UMBRAL_DIF  = 8
ATTRIBUTE_ID= 2
REGIONS     = [[2,5,5,7],[4,1,7,2]]
VERIFY_COLOR= ['gris', 'plata'] 

# parameters client rabbitMQ
RABBITMQ_QUEUE  = 'frame_register_queue'
EXCHANGE_TYPE   = 'fanout'
EXCHANGE_ROUTING= ''  # En fanout, no se usa routing_key
EXCHANGE_DURABLE= True
AMQP_URL        = 'amqp://root:winempresas@10.23.63.79:5672/%2F'
EXCHANGE_IN     = 'objs_candidate'
QUEUE_IN        = 'objscolor'
EXCHANGE_OUT    = 'attributes'

# Variables JSON
DATA_CAMERA                 = "camera_id"
DATA_EPOCH_FRAME            = "epoch_frame" 
DATA_FUNCIONALIDAD          = "funcionality"
DATA_CANDIDATO              = "candidate_frame"
DATA_STATUS_FRAME           = "status_frame"
DATA_INIT_TIME              = "init_time_frame"
DATA_FINAL_TIME             = "final_time_frame"
DATA_N_OBJECTOS             = "n_objects"
DATA_OBJESTOS_LIST          = "object_dict"
DATA_OBJETO_CATEGORIA       = "category" 
DATA_OBJETO_COORDENADAS     = "coords"
DATA_OBJETO_PRECISION       = "accuracy"
DATA_OBJETO_EPOCH_OBJECT    = "epoch_object"
DATA_OBJETO_COORDS_ATTRIBUTE= "coords_attribute"
DATA_OBJETO_CANDIDATO       = "candidate"
DATA_ATRIBUTO_INIT_TIME     = "init_time"
DATA_ATRIBUTO_ID            = "attribute_id"
DATA_ATRIBUTO_DESCRIPITON   = "description"
DATA_ATRIBUTO_ACCURACY      = "accuracy_attribute"
DATA_ATRIBUTO_FINAL_TIME    = "final_time"
DATA_ATRIBUTO_STATUS        = "status_attribute"
DATA_OBJETO_ID_CONCATENADO  = "object_id"

# parameters log 
FILE_NAME_LOG   = 'color'
FILE_LOG_PUBLI  = 'publisher'
FILE_LOG_CONSUM = 'consumer'
FILE_PATH_LOG   = './log'
LEVEL_LOG       = logging.DEBUG

# parameters save image
FILE_DATE   = '%Y-%m-%d'
FILE_HOUR   = '%H'
FILE_OUTPUT = 'output'
FILE_FRAME  = 'frames'
FILE_OBJECT = 'objects'
FILE_FORMAT = 'jpeg'

EPOCH_FORMAT= 1000

# colors
color_ranges = {
    "rojo"       : [(155, 50, 70), (180, 255, 255)],
    "naranja"    : [(0, 50, 70), (17, 255, 255)],  
    "amarillo"    : [(16, 50, 70), (35, 255, 255)],  
    "verde"     : [(35, 50, 70), (85, 255, 255)],  
    "celeste": [(85, 50, 70), (100, 255, 255)], 
    "azul"      : [(100, 50, 70), (140, 255, 255)], 
    "rosado"      : [(140, 50, 70), (155, 255, 255)],
    "negro"     : [(90, 0, 0), (140, 50, 100)],  
    "gris"      :  [(30, 0, 90), (160, 60, 240)],   
    "blanco"     : [(0, 0, 240), (180, 20, 255)]
    }

# parameters umbral times
UMBRAL_TIME_CAPTURE = 0.60
UMBRAL_TIME_RCBD_IMG= 0.50
UMBRAL_TIME_SAVE_IMG= 0.50
UMBRAL_TIME_FILT_IMG= 0.20
UMBRAL_TIME_SEND_MSG= 0.05

# parameters logger error
LOG_CONFIG_CAM    = '300 - Configuracion de camara'
LOG_CONFIG_RABBIT = '330 - Configuracion de rabbitMQ'
LOG_RECIB_MSG     = '331 - Mensaje no recibido'
LOG_SEND_MSG      = '331 - Mensaje no publicado'

LOG_PROCESS_IMG   = '410 - Procesamiento de imagen'
LOG_TIME_FILTER   = '411 - Tiempo de decision de frame candidato'
LOG_SAVE_IMG      = '412 - Escritura de imagen'
LOG_READ_IMG      = '413 - Lectura de imagen'
LOG_TIME_SAVE     = '414 - Tiempo de escritura'
LOG_TIME_READ     = '415 - Tiempo de lectura'

LOG_CON_RTSP      = '403 - Conexion a la camara'
LOG_FRAME         = '404 - Captura del fotograma'
LOG_RECONNECT     = '406 - Reconexion de camara'
LOG_PARAMETERS    = '407 - Al inicializar parametros'
LOG_TIME_READ_CAP = '408 - Tiempo captura del frame'

LOG_CON_RABBIT    = '430 - Sin conexion a RabbitMQ'
LOG_PUBLISHER     = '431 - Publicacion del mensaje'
LOG_CONSUMER      = '431 - Obtencion del mensaje'
LOG_TIME_SEND     = '432 - Tiempo de envio de frame'
LOG_CHANNEL       = '433 - Canal no abierto'
LOG_IOLOOP        = '434 - IOLoop exited'
LOG_CHANNEL_CLOSE = '435 - Canal cerrado'
LOG_CONNECT_CLOSE = '436 - Conexion cerrada'

LOG_MAIN_BUCLE    = '450 - Inesperado en bucle principal'
LOG_FUNC_FLAG     = '451 - Discriminacion del frame candidato'
LOG_FUNC_COLOR    = '452 - Deteccion del color'
