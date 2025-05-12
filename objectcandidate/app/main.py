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
publisher = None 
coords_cameras = {}
camera_locks = {}  # Locks por cámara
global_lock = threading.Lock()  # Lock para acceder a camera_locks

# Pool de conexiones global para Redis
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT
)

def getPath(epoch, camera_id):
    day, hour = getDate(epoch / EPOCH_FRAME_FORMAT)
    output_path = f"/output/{camera_id}/{day}/{hour}/frames/{epoch}.jpeg"
    logger2.info(f"getPath: {output_path}")
    return output_path

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
        
def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def saveImg(r, img, objeto_id, camera_id, epochframe):  
     
    init_time_test = time.time()
    _, buffer = cv2.imencode('.jpeg', img) #cv2.imencode('.webp', frame)  # Codificación en formato JPEG
    logger.warning(f'{epochframe} frame_bytes es {time.time()-init_time_test} para la camara {camera_id}')
    init_time_test = time.time()
    jpg_bytes = buffer.tobytes()
    logger.warning(f'compressed_bytes es {time.time()-init_time_test} para la camara {camera_id}')
    init_time_test = time.time()
    objeto_id = int(f"1{objeto_id}") #int(f"1{objeto_id}")
    object_key = f"{camera_id}{epochframe}:object:{objeto_id}"
    if r.exists(f"{camera_id}{epochframe}") and not r.exists(objeto_id):
        r.set(objeto_id, jpg_bytes, ex=4) #r.hset(camera_id, objeto_id, jpg_bytes)
        r.sadd(f"{camera_id}{epochframe}:object", object_key)
    logger.warning(f'{objeto_id} hset es {time.time()-init_time_test} para la camara {camera_id}')
    # day, hour = getDate(epoch_frame/EPOCH_FRAME_FORMAT)
    # output_path = f"/output/{camera_id}/{day}/{hour}/objects"

    # os.makedirs(output_path, exist_ok=True)

    # try:
    #     tiempo_inicio = time.time()
    #     success = cv2.imwrite(f"{output_path}/{epoch_object}.jpeg",frame) 
    #     tiempo_elapsed = time.time() - tiempo_inicio
    #     if not success:
    #         raise IOError("No se pudo guardar la imagen.")
    #     logger.info(f"Imagen guardada en {tiempo_elapsed:.6f} segundos")
    # except IOError as e:
    #     logger.error(f"Error al guardar imagen: {e}")

def is_inside(new_coords, old_coords):
    """Retorna True si new_coords está dentro de old_coords."""
    x1, y1, x2, y2 = new_coords
    x1_old, y1_old, x2_old, y2_old = old_coords
    return (x1_old <= x1 <= x2_old and y1_old <= y1 <= y2_old and
            x1_old <= x2 <= x2_old and y1_old <= y2 <= y2_old)

def expand_bbox(coords, padding=PADDING):
    """Expande las coordenadas del bounding box en 'padding' píxeles."""
    x1, y1, x2, y2 = coords
    alto = y2-y1
    ancho = x2-x1
    return [x1 - int(padding*ancho), y1 - int(padding*alto), x2 + int(padding*ancho), y2 + int(padding*alto)]

def obtener_dimensiones(imagen):
    altura, ancho = imagen.shape[:2]  # Siempre existen altura y ancho
    canales = 1 if len(imagen.shape) == 2 else imagen.shape[2]  # Si es gris, canales = 1
    
    return (altura, ancho, canales)

def guardar_objetos(camera_id, data):
    logger2.info(f"data: {data}")
    
    r = redis.Redis(connection_pool=redis_pool, decode_responses=False)

    if DATA_EPOCH_FRAME in data:
        epoch_frame = data[DATA_EPOCH_FRAME]
        # file_path = getPath(epoch_frame, camera_id)
        
        img, success = load_image(r, camera_id,data[DATA_EPOCH_FRAME])
        dimensiones = obtener_dimensiones(img)
        data[DATA_FRAME_DIMENSIONES] = dimensiones
        if not success:
            return None
        
        for categoria, boxes in data[DATA_OBJETOS_DICT].items():
            for box in boxes:
                if box[DATA_OBJETO_CANDIDATO] == True:
                    coords = box[DATA_OBJETO_COORDENADAS]
                    img_slicing = img[coords[1]:coords[3], coords[0]:coords[2]]
                    # _, image = cv2.imencode('.jpeg', img)
                    # image_bytes = image.tobytes()
                    # image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    # box[DATA_OBJETO_IMG] = image_base64
                    saveImg(r, img_slicing, box[DATA_OBJETO_ID_CONCATENADO],camera_id, data[DATA_EPOCH_FRAME])
    logger2.info(f"Data actual procesada: {data} para camara {data[DATA_CAMERA]}")
    publish_detection_result(data)
            
def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    try:
        # Sincronización por cámara
        # with global_lock:
        #     if cam_id not in camera_locks:
        #         camera_locks[cam_id] = threading.Lock()
        #     lock = camera_locks[cam_id]
        
        # with lock:  # Bloqueo exclusivo para esta cámara
            # Verificación atómica de epoch_frame
        current_epoch = coords_cameras.get(cam_id, {}).get(DATA_EPOCH_FRAME, 0)
        if data[DATA_EPOCH_FRAME] <= current_epoch:
            logger2.info(f"Frame obsoleto para cámara {cam_id}: {data}")
            return
        
        data_actual = coords_cameras.get(cam_id, {})

        logger2.info(f"Coords actuales: {data_actual} para camara {cam_id}")
        inicio_tiempo = time.time()
        # Iterar sobre cada categoría y sus cajas en la nueva data
        for categoria, new_boxes in data[DATA_OBJETOS_DICT].items():
            for i, new_box in enumerate(new_boxes):
                new_conf = new_box[DATA_OBJETO_PRECISION]
                new_coords = new_box[DATA_OBJETO_COORDENADAS]

                # Bandera para indicar si se encontró coincidencia con la data anterior
                match_found = False
                
                new_box[DATA_OBJETO_CANDIDATO] = True
                new_box[DATA_OBJETO_STATUS] = False
                new_box[DATA_OBJETO_ATRIBUTOS_LIST] = [1, 2]
                new_box[DATA_OBJETO_ID_CONCATENADO] = f"{cam_id}{data[DATA_EPOCH_FRAME]}{categoria}{i}"
                new_box[DATA_OBJETO_ID_TRACKING] = new_box[DATA_OBJETO_ID_CONCATENADO]
                # new_box[DATA_OBJETO_ID_CONCATENADO] = f"{cam_id}{data[DATA_EPOCH_FRAME]}{new_box[DATA_OBJETO_EPOCH_OBJECT]}"
                #str(cam_id) + str(data[DATA_EPOCH_FRAME]) + str(new_box[DATA_OBJETO_EPOCH_OBJECT])

                # Si la categoría existe en la data anterior, comparo cada box
                if categoria in data_actual.get(DATA_OBJETOS_DICT, {}):
                    for old_box in data_actual[DATA_OBJETOS_DICT][categoria]:
                        old_coords = old_box[DATA_OBJETO_COORDENADAS]
                        if is_inside(new_coords, expand_bbox(old_coords)):
                            logger2.info(f"Match-------------------------{old_box[DATA_OBJETO_ID_TRACKING]}")
                            new_box[DATA_OBJETO_ID_TRACKING] = old_box[DATA_OBJETO_ID_TRACKING]
                            
                            # Comparar precisión: si la nueva es mayor, se desmarca el candidato anterior
                            if new_conf > old_box.get(DATA_OBJETO_BEST_ACCURACY,0):
                                old_box[DATA_OBJETO_CANDIDATO] = False
                                old_box[DATA_OBJETO_STATUS] = True
                                new_box[DATA_OBJETO_BEST_ACCURACY] = new_conf
                            else:
                                new_box[DATA_OBJETO_BEST_ACCURACY] = old_box[DATA_OBJETO_BEST_ACCURACY]
                                new_box[DATA_OBJETO_CANDIDATO] = False

                            match_found = True
                            break
        logger.info(f"Tiempo de procesamiento {time.time() - inicio_tiempo}")
        if data_actual != {}:
            # logger2.info(f"Data Procesada: {data_actual}")
            thread = threading.Thread(target=guardar_objetos, args=(cam_id, data_actual))
            thread.start()
            # guardar_objetos(cam_id, data_actual)
            
            
        # Actualizamos la información de coordenadas para la cámara
        coords_cameras[cam_id] = data
        return True
    
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def imprimir_tipos(diccionario, nivel=0):
    for clave, valor in diccionario.items():
        logger.info("  " * nivel + f"La clave '{clave}' tiene un valor de tipo: {type(valor)}")
        if isinstance(valor, dict):  # Si el valor es otro diccionario, recorrerlo recursivamente
            imprimir_tipos(valor, nivel + 1)

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    procesar_mensaje(body)
    # thread = threading.Thread(target=procesar_mensaje, args=(body,))
    # thread.start()

def procesar_mensaje(body):
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Datos recibidos {data}")
        procesamiento_coordenadas(data)  # Procesamiento sincronizado
    except Exception as e:
        logger.error(f"Error procesando mensaje: {str(e)}")

# def rabbitmq_message_callback(channel, basic_deliver, properties, body):
#     try:
#         data = json.loads(body.decode('utf-8'))
#         logger.info(f"Datos {threading.get_ident()} recibidos: {data}")
#         # imprimir_tipos(data)
                       
#         # Se procesa la información y se publica el resultado
#         thread = threading.Thread(target=procesamiento_coordenadas, args=(data,))
#         thread.start()

#         logger.info(f"Mensaje recibido para cámara {data[DATA_CAMERA]}: {data} Procesando")
    
#     except Exception as e:
#         logger.error(f"Error processing RabbitMQ message: {str(e)}")

def publish_detection_result(result):
    """
    Callback que se ejecuta al finalizar el procesamiento de detecciones.
    Publica el resultado (si existe) mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando {threading.get_ident()} resultado de detección vía publicador asíncrono: {result}")
        if publisher is not None:
            publisher.publish_async(result)
        else:
            logger.error("Publicador no disponible para publicar el resultado.")

def main():
    global publisher
    publisher = ExamplePublisher(AMQP_URL)
    publisher.start()

    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        publisher.stop()

if __name__ == "__main__":
    main()