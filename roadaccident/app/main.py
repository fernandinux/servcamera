import time
from transformers import BlipProcessor, BlipForQuestionAnswering
from torch.multiprocessing import Pool, current_process  # type: ignore
import threading
import json
import cv2  # type: ignore
from datetime import datetime
import redis # type: ignore
import numpy as np # type: ignore
import re

# Importamos la configuración y la función de logging
from config import *
from config_logger import configurar_logger
# Importamos el consumer modificado y el publicador
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher


# Configuración global
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)
logger2 = configurar_logger(name="procesamiento", log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
consumer = None
publisher_instance = None
processor_instance = None
model_instance = None
coords_cameras = {}
zonas_data = {
    "10" : {COORDENADAS_ZONA_INTERES : [(0.0, 0.3086), (1.0, 0.0438), (1.0, 1.0), (0.0, 1.0)], "recurencia_time" : 60000},
    "27" : {COORDENADAS_ZONA_INTERES : [(1.0, 1.0), (1.0, 0.4213), (0.2478, 0.0647), (0.2714, 1.0)], "recurencia_time" : 60000},
    "35" : {COORDENADAS_ZONA_INTERES : [(0.0, 0.1827), (0.6268, 0.0726), (0.7139, 1.0), (0.0, 1.0)], "recurencia_time" : 60000}
}
# Diccionario que almacena el estado de cada cámara.
# camera_state[camera_id] = {"last_epoch": <int>, "priority": <bool>}
camera_state = {}

# Única pila para almacenar los mensajes.
# Se usa append() para encolar normalmente y insert(0, …) para encolar con prioridad.
stack = []
# Pool de conexiones global para Redis
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT
)

def init_worker():
    global processor_instance, model_instance, publisher_instance
    try:
        worker_name = current_process().name
        logger.info(f"🔄 Inicializando modelo en el worker {worker_name}...")
        processor_instance = BlipProcessor.from_pretrained(PATH_MODEL)
        model_instance = BlipForQuestionAnswering.from_pretrained(PATH_MODEL).to('cuda')

        publisher_instance = ExamplePublisher(AMQP_URL)
        publisher_instance.start()
        
        logger.info(f"✅ Modelo cargado en el worker {worker_name}.")
    except Exception as e:
        logger.exception("Error inicializando worker")
        raise

def getPath(epoch, camera_id):
    day, hour = getDate(epoch / EPOCH_FRAME_FORMAT)
    output_path = f"/output/{camera_id}/{day}/{hour}/frames/{epoch}.jpeg"
    logger2.info(f"getPath: {output_path}")
    return output_path

def load_image(r, cam_id, epoch):
    try:
        inicio_tiempo = time.time()
        
        image_bytes = r.get(f'{cam_id}{epoch}')  # o r.hget(cam_id, epoch)
        if not image_bytes:
            logger2.error(f"Frame {epoch} no existe en Redis")
            return None, False
        
        # logger2.info(f"Tiempo obtención Redis: {time.time() - inicio_tiempo:.3f}s")
        
        try:
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            # logger2.info(f"Tiempo buffer to array: {time.time() - inicio_tiempo:.3f}s")
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            logger2.info(f"Tiempo array to img: {time.time() - inicio_tiempo:.3f}s")
            
            if img is None:
                logger2.error("Formato de imagen inválido")
                return None, False
        except Exception as e:
            logger2.exception("Error decodificando imagen")
            return None, False
        
        return img, True
        
    except Exception as e:
        logger2.exception("Error al abrir imagen")
        return None, False

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def zona_modificada(img, camera_id):
    height, width = img.shape[:2]
    coords = (zonas_data.get(camera_id)).get(COORDENADAS_ZONA_INTERES)
    polygon = np.array(
        [(int(x * width), int(y * height)) for (x, y) in coords],
        dtype=np.int32
    )

    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)

    img = cv2.bitwise_and(img, img, mask=mask)
    
    # filename = f"/images/{camera_id}_{epoch_frame}.jpeg"
    # logger2.info(filename)
    # cv2.imwrite(filename,img)
    return img

def test_id_tracking(data):
    objetos = data[DATA_OBJETOS_DICT]
    for categoria, boxes in objetos.items():
        for objeto in boxes:
            id_tracking = objeto[DATA_OBJETO_ID_TRACKING]
            first_epoch_object = int(str(id_tracking)[-13:])
            epoch_object = objeto[DATA_OBJETO_EPOCH_OBJECT]
            if epoch_object - first_epoch_object >= TIEMPO_ENTRE_FRAMES_ALERTA:
                return True
    logger.info(f"No epoca del objeto long time. primera epoca del objeto: {first_epoch_object}, epoca actual: {epoch_object}")
    return False
def procesarFrame(data):
    camera_id = data[DATA_CAMERA]
    logger2.info(f"Procesando: {data}")
    
    try:
        data_actual = coords_cameras.get(camera_id, {})
        contador_actual = data_actual.get(ALERT_CONTADOR_CONCURRENCIA, 0)
        r = redis.Redis(connection_pool=redis_pool, decode_responses=False)

        epoch_frame = data[DATA_EPOCH_FRAME]
        
        img, success = load_image(r, camera_id, epoch_frame)
        
        if not success:
            return None
        
        # logger2.info(zonas_data)
        
        if zonas_data.get(camera_id) is not None:
            inicio_tiempo = time.time()
            img = zona_modificada(img, camera_id)
            logger2.info(f"modificando zona {camera_id} tiempo: {time.time() - inicio_tiempo}")
            
        inicio_tiempo = time.time()
        inputs = processor_instance(img, PROMPT, return_tensors="pt").to("cuda")
        out = model_instance.generate(**inputs)
        result_text = processor_instance.decode(out[0], skip_special_tokens=True)
        elapsed_time = time.time() - inicio_tiempo
        pattern = r'^\s*yes[\.\?!]*\s*$'
        alert = {
                ALERT_CAMERA_ID: data.get(DATA_CAMERA, 0),
                ALERT_TYPE: ALERT_TYPE_VALUE_DEFAULT,
                # 'epoch_object': new_box.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                ALERT_EPOCH_FRAME: data.get(DATA_EPOCH_FRAME, 0),
                # 'object_id': new_box.get(DATA_OBJETO_ID_CONCATENADO, 0),
                ALERT_MESSAGE: f'Accidente de transito detectado {result_text}',
                ALERT_ELAPSED_TIME: elapsed_time,
                'epoch_object': 0,
                'object_id': 0
            }
        
        if data_actual.get(FIRST_EPOCH) is not None:
            alert[FIRST_EPOCH] = data_actual.get(FIRST_EPOCH)
        
        logger2.info(f"modelo result: {result_text} de camara {camera_id} en {elapsed_time} segundos")
        if re.match(pattern, result_text, re.IGNORECASE) and data.get(DATA_N_OBJECTOS) != 0:
            contador = contador_actual + 1
            alert[ALERT_CONTADOR_CONCURRENCIA] = contador
            logger2.info(f"contador: {contador}")
            if contador == 1:
                alert[FIRST_EPOCH] = epoch_frame
                
            if contador < RECURRENCIA_ALERTA and contador >= RECURRENCIA_NOTIFICACION:
                categoria = 1
                alert[ALERT_CATEGORIA] = categoria
                logger2.info(f"Publicando {alert}")
                publisher_instance.publish_async(alert)
                
            elif contador >= RECURRENCIA_ALERTA and epoch_frame - alert[FIRST_EPOCH] > TIEMPO_ID_TRACKING_ALERTA and test_id_tracking(data):
                categoria = 2
                alert[ALERT_CATEGORIA] = categoria
                logger2.info(f"Publicando {alert}")
                publisher_instance.publish_async(alert)
                
            coords_cameras[camera_id] = alert
            return True
        else:
            contador = 0
            categoria = 0
            alert[ALERT_CATEGORIA] = categoria
            alert[ALERT_CONTADOR_CONCURRENCIA] = contador

            coords_cameras[camera_id] = alert
            return False
        # global consumer
        # if consumer:
        #     consumer._consumer.purge_queue()  # Se invoca correctamente el método de purga
        #     logger2.info(f"limpio")
    except Exception as e:
        logger2.error(f"Error en procesamiento: {str(e)}")
        return None
    
def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    procesar_mensaje(body)
    # Alternativamente, se puede usar threading para procesar en paralelo:
    # thread = threading.Thread(target=procesar_mensaje, args=(body,))
    # thread.start()
def process_mensaje_queue():
    global stack
    while True:
        if stack:
            # Extraer el primer mensaje de la pila (FIFO)
            msg = stack.pop(0)
            camera_id = msg.get("camera_id")
            result = procesarFrame(msg)
            camera_state[camera_id] = {"last_epoch": msg.get("epoch_frame"), "priority": result}
            
        else:
            time.sleep(0.1)


def procesar_mensaje(body):
    try:
        global camera_state, stack
        data = json.loads(body.decode('utf-8'))
        
        logger.info(f"Datos recibidos {data}")
        
        camera_id = data.get(DATA_CAMERA)
        current_epoch = data.get(DATA_EPOCH_FRAME)
        state = camera_state.get(camera_id, {"last_epoch": None, "priority": False})
        if state["last_epoch"] is None:
            camera_state[camera_id] = {"last_epoch": data.get("epoch_frame"), "priority": False}
        elif (current_epoch - state["last_epoch"] >= TIEMPO_PARA_PREDICT):
            camera_state[camera_id] = {"last_epoch": data.get("epoch_frame"), "priority": False}
            if state["priority"]:
                stack.insert(0, data)
                logger.info("Insertando con prioridad")
            else:
                stack.append(data)
                logger.info("Insertando al final de la pila")

                
    except Exception as e:
        logger.error(f"Error procesando mensaje: {str(e)}")

def publish_detection_result(result):
    """
    Callback que se ejecuta al finalizar el procesamiento de detecciones.
    Publica el resultado (si existe) mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando {threading.get_ident()} resultado de detección vía publicador asíncrono: {result}")
        if publisher_instance is not None:
            publisher_instance.publish_async(result)
        else:
            logger.error("Publicador no disponible para publicar el resultado.")

def main():
    global consumer
    init_worker()
    
    queue_thread = threading.Thread(target=process_mensaje_queue, daemon=True)
    queue_thread.start()
    
    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        if publisher_instance:
            publisher_instance.stop()

if __name__ == "__main__":
    main()
