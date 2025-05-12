import threading
import json
import cv2  # type: ignore
import time
from datetime import datetime
import redis # type: ignore
import numpy as np # type: ignore
# Importamos la configuración y la función de logging
from config import *
from config_logger import configurar_logger
# Importamos el consumer modificado
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración global
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)
logger2 = configurar_logger(name="pruebas", log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
global contador_fhd, contador_hd
contador_fhd = 0
contador_hd = 0

# Pool de conexiones global para Redis
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT
)

def load_image(r, cam_id, epoch):
    try:
        inicio_tiempo = time.time()
        
        image_bytes = r.get(f'{cam_id}{epoch}') # r.hget(cam_id, epoch)
        if not image_bytes:
            logger.error(f"Frame {epoch} no existe en Redis")
            return None, False
        
        logger.info(f"Tiempo obtención Redis: {time.time() - inicio_tiempo:.3f}s")
        
        try:
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            logger.info(f"Tiempo buffer to array: {time.time() - inicio_tiempo:.3f}s")
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            logger.info(f"Tiempo array to img: {time.time() - inicio_tiempo:.3f}s")
            
            if img is None:
                logger.error("Formato de imagen inválido")
                return None, False
        except Exception as e:
            logger.exception("Error decodificando imagen")
            return None, False
        
        return img, True
        
    except Exception as e:
        logger.exception("Error al abrir imagen")
        
def obtener_dimensiones(imagen):
    altura, ancho = imagen.shape[:2]  # Siempre existen altura y ancho
    canales = 1 if len(imagen.shape) == 2 else imagen.shape[2]  # Si es gris, canales = 1
    
    return (altura, ancho, canales)

def procesar(camera_id, data):
    
    global  contador_fhd, contador_hd
    logger2.info(f"data: {data}")
    
    r = redis.Redis(connection_pool=redis_pool, decode_responses=False)

    epoch_frame = data[DATA_EPOCH_FRAME]
    # file_path = getPath(epoch_frame, camera_id)
    
    img, success = load_image(r, camera_id,data[DATA_EPOCH_FRAME])
    if success:
        dimensiones = obtener_dimensiones(img) #(altura, ancho, canales)
            
        if dimensiones[0] == 1080:
            contador_fhd += 1
        elif dimensiones[0] == 720:
            contador_hd += 1
            
        logger2.info(f"Dimensions {dimensiones[0]}. Count FHD: {contador_fhd}. Count HD: {contador_hd}")


def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    # procesar_mensaje(body)
    thread = threading.Thread(target=procesar_mensaje, args=(body,))
    thread.start()

def procesar_mensaje(body):
    try:
        data = json.loads(body.decode('utf-8'))
        cam_id = data[DATA_CAMERA]
        logger.info(f"Datos recibidos {data}")
        procesar(cam_id, data)  # Procesamiento sincronizado
    except Exception as e:
        logger.error(f"Error procesando mensaje: {str(e)}")


def main():

    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")


if __name__ == "__main__":
    main()