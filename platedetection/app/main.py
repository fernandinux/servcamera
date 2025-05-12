import os
import threading
import queue
import json
import cv2  # type: ignore
import time
from datetime import datetime
from ultralytics import YOLO  # type: ignore
import torch.multiprocessing as mp  # type: ignore
from torch.multiprocessing import Pool, current_process  # type: ignore
import logging
import functools
import redis
import numpy as np

# Importamos la configuración y la función de logging
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración global
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 
yolo_instance = None
pool = None

# Tamaño máximo de la cola para almacenar arrays de imagen de candidatos
MAX_QUEUE_SIZE = 300
# Cada elemento de candidate_queue es una tupla: (img, candidate, frame_data)
# candidate_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
candidate_queue = queue.Queue()

# Pool de conexiones global para Redis
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT
)


def saveImg(r, img, placa_id, camera_id, epochframe):
    init_time_test = time.time()
    _, buffer = cv2.imencode('.jpeg', img) #cv2.imencode('.webp', frame)  # Codificación en formato JPEG
    logger.warning(f'{epochframe} frame_bytes es {time.time()-init_time_test} para la camara {camera_id}')
    init_time_test = time.time()
    jpg_bytes = buffer.tobytes()
    logger.warning(f'compressed_bytes es {time.time()-init_time_test} para la camara {camera_id}')
    init_time_test = time.time()
    placa_id = int(f"2{placa_id}")
    plate_key = f"{camera_id}{epochframe}:plate:{placa_id}"
    if r.exists(f"{camera_id}{epochframe}") and not r.exists(placa_id):
        r.set(placa_id, jpg_bytes, ex=4) #r.hset(camera_id, placa_id, jpg_bytes)
        r.sadd(f"{camera_id}{epochframe}:plate", plate_key)
    
    logger.warning(f'{placa_id} set es {time.time()-init_time_test} para la camara {camera_id}')
    # """Guarda la imagen recortada en la carpeta 'plates' dentro del folder dado."""
    # output_path = os.path.join(folder, "plates")
    # os.makedirs(output_path, exist_ok=True)
    # try:
    #     file_path = os.path.join(output_path, f"{epoch_plate}.jpeg")
    #     inicio_tiempo = time.time()
    #     if not cv2.imwrite(file_path, frame):
    #         raise IOError("No se pudo guardar la imagen.")
    #     logger.info(f"Guardando imagen recortada en: {file_path} en {time.time() - inicio_tiempo}: ")
    # except IOError as e:
    #     logger.error(f"Error al guardar imagen: {e}")

def init_worker():
    """Inicializa el modelo YOLO en cada proceso worker."""
    global yolo_instance
    try:
        worker_name = current_process().name
        logger.info(f"🔄 Inicializando modelo en el worker {worker_name}...")
        yolo_instance = YOLO(YOLO_MODEL).to("cuda")
        logger.info(f"✅ Modelo cargado en el worker {worker_name}.")
    except Exception as e:
        logger.error(f"Error inicializando worker: {str(e)}")
        raise

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def get_folder_path(data):
    """Obtiene la carpeta de almacenamiento a partir del frame (DATA_EPOCH_FRAME)."""
    try: 
        day, hour = getDate(data[DATA_EPOCH_FRAME] / EPOCH_FRAME_FORMAT)
        output_path = f"/output/{data[DATA_CAMERA]}/{day}/{hour}/"
        logger.info(f"Folder path obtenido: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error en get_folder_path: {str(e)}")
        return None

def read_candidate_image(frame_data, candidate):
    """
    Hilo que lee la imagen del objeto candidato (usando cv2.imread) y la encola.
    Se utiliza el campo DATA_OBJETO_EPOCH_OBJECT para construir el nombre de la imagen.
    """
    try:
        # file_path = os.path.join(folder, "objects", f"{candidate[DATA_OBJETO_EPOCH_OBJECT]}.jpeg")
        # logger.info(f"Leyendo imagen candidata desde: {file_path}")
        # img = cv2.imread(file_path)
        r = redis.Redis(connection_pool=redis_pool, decode_responses=False)
        
        inicio_tiempo = time.time()
        objeto_id= candidate[DATA_OBJETO_ID_CONCATENADO]
        objeto_id = int(f"1{objeto_id}")
        
        image_bytes = r.get(objeto_id)
        if not image_bytes:
            logger.error(f"Objeto {objeto_id}  no existe en Redis")
            return None, False
        
        logger.info(f"Tiempo obtención Redis: {time.time() - inicio_tiempo:.3f}s")
        
        try:
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            logger.info(f"Tiempo buffer to array: {time.time() - inicio_tiempo:.3f}s")
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            logger.info(f"Tiempo array to img: {time.time() - inicio_tiempo:.3f}s")
            
            if img is None:
                logger.error("Formato de imagen inválido")
                return 
        except Exception as e:
            logger.exception("Error decodificando imagen")
            return 
        
        if img is None:
            logger.error(f"No se pudo leer la imagen")
            with frame_data["_cond"]:
                frame_data["pending_candidates"] -= 1
                frame_data["_cond"].notify_all()
            return
        if candidate_queue.full():
            logger.warning(f"La cola está llena (máximo {MAX_QUEUE_SIZE}). Se descarta la imagen: {objeto_id}")
            with frame_data["_cond"]:
                frame_data["pending_candidates"] -= 1
                frame_data["_cond"].notify_all()
            return
        candidate_queue.put((img, candidate, frame_data))
        logger.info(f"Imagen encolada. Tamaño actual de la cola: {candidate_queue.qsize()}/{MAX_QUEUE_SIZE}")
    except Exception as e:
        logger.error(f"Error en read_candidate_image: {str(e)}")
        with frame_data["_cond"]:
            frame_data["pending_candidates"] -= 1
            frame_data["_cond"].notify_all()

def process_candidate_image(img):
    """
    Función que se ejecuta en un worker multiproceso.
    Procesa la imagen con yolo.predict y retorna una tupla (results, img).
    """
    try:
        results = yolo_instance.predict(source=img, conf=CONF, verbose=False)
        return (results, img)
    except Exception as e:
        logger.error(f"Error en process_candidate_image: {str(e)}")
        return (None, img)

def candidate_result_callback(result_tuple, candidate, frame_data):
    """
    Callback del worker que actualiza el objeto candidato con el resultado de la inferencia.
    Se actualizan los campos:
      - DATA_OBJETO_COORDS_ATTRIBUTE: coordenadas del primer objeto detectado.
      - DATA_ATRIBUTO_INIT_TIME: epoch actual multiplicado por EPOCH_PLATE_FORMAT.
      - DATA_ATRIBUTO_STATUS: 0.
    Si no hay detección, se asignan valores por defecto.
    Además, si se detectó el objeto, se recorta la imagen según las coordenadas y se guarda.
    """
    try:
        results, original_img = result_tuple
        if results is not None and results[0].boxes:
            # Extraer coordenadas del primer box detectado
            box = results[0].boxes[0]
            coords = list(map(int, box.xyxy[0]))
            epoch_plate = int(time.time() * EPOCH_PLATE_FORMAT)
            candidate[DATA_OBJETO_COORDS_ATTRIBUTE] = coords
            candidate[DATA_ATRIBUTO_INIT_TIME] = epoch_plate
            candidate[DATA_ATRIBUTO_STATUS] = 0
            logger.info(f"Detección exitosa. coords: {coords}, init_time: {epoch_plate}, status: 0")
            # Recortar la imagen usando las coordenadas
            x1, y1, x2, y2 = coords
            cropped_img = original_img[y1:y2, x1:x2]
            # Usar el folder almacenado en el frame para guardar la imagen recortada
            r = redis.Redis(connection_pool=redis_pool, decode_responses=False)
            
            saveImg(r, cropped_img, candidate[DATA_OBJETO_ID_CONCATENADO], frame_data[DATA_CAMERA], frame_data[DATA_EPOCH_FRAME])
        else:
            # Sin detección: asignar valores por defecto
            epoch_plate = int(time.time() * EPOCH_PLATE_FORMAT)
            candidate[DATA_OBJETO_COORDS_ATTRIBUTE] = None
            candidate[DATA_ATRIBUTO_INIT_TIME] = epoch_plate
            candidate[DATA_ATRIBUTO_STATUS] = 0
            candidate[DATA_ATRIBUTO_ID] = 1
            candidate[DATA_ATRIBUTO_DESCRIPITON] = None
            candidate[DATA_ATRIBUTO_ACCURACY] = None
            candidate[DATA_ATRIBUTO_FINAL_TIME] = int(time.time() * EPOCH_PLATE_FORMAT)
            logger.info("No se detectó objeto. Se asignan valores por defecto a candidate.")
    except Exception as e:
        logger.error(f"Error en candidate_result_callback: {str(e)}")
    finally:
        with frame_data["_cond"]:
            frame_data["pending_candidates"] -= 1
            frame_data["_cond"].notify_all()

def candidate_queue_processor():
    """
    Hilo que procesa continuamente la cola global de candidatos.
    Extrae cada (img, candidate, frame_data) y envía la imagen a un worker en multiproceso.
    """
    while True:
        try:
            img, candidate, frame_data = candidate_queue.get()
            logger.info(f"Procesando imagen candidata con yolo.predict. Cola actual: {candidate_queue.qsize()}/{MAX_QUEUE_SIZE}")
            pool.apply_async(process_candidate_image, args=(img,),
                             callback=functools.partial(candidate_result_callback, candidate=candidate, frame_data=frame_data))
            candidate_queue.task_done()
        except Exception as e:
            logger.error(f"Error en candidate_queue_processor: {str(e)}")
            candidate_queue.task_done()
        time.sleep(0.01)

def process_message(data):
    """
    Función que se ejecuta en un hilo por cada mensaje (frame) recibido.
    Obtiene la carpeta de almacenamiento a partir del frame y, por cada objeto candidato,
    crea un hilo que lee la imagen y la encola para inferencia.
    Se utiliza un contador y Condition para esperar a que se procesen todos los candidatos.
    Finalmente, se envía el mensaje completo (con resultados actualizados) mediante el publicador.
    """
    try:
        folder = get_folder_path(data)
        if folder is None:
            logger.error("No se pudo obtener el folder de almacenamiento. Se omite el procesamiento.")
            return
        
        # Inicializar contador de candidatos pendientes y un Condition para sincronización
        lock = threading.Lock()
        cond = threading.Condition(lock)
        data["pending_candidates"] = 0
        data["_cond"] = cond

        # Recorrer la lista de objetos candidatos en el frame
        for cat, boxes in data[DATA_OBJETOS_DICT].items():
            for candidate in boxes:
                if candidate.get(DATA_OBJETO_CANDIDATO, False):
                    with cond:
                        data["pending_candidates"] += 1
                    # Crear un hilo para leer la imagen del candidato y encolarla
                    threading.Thread(
                        target=read_candidate_image, 
                        args=(data, candidate),
                        daemon=True
                    ).start()

        # Esperar a que se procesen todos los candidatos
        with cond:
            while data["pending_candidates"] > 0:
                cond.wait(timeout=0.1)
        # Publicar el mensaje del frame (con los resultados actualizados)
        del data["_cond"]
        logger.info(f"Publicando frame. {data}")
        publisher.publish_async(data)
    except Exception as e:
        logger.error(f"Error en process_message: {str(e)}")

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    """
    Callback para cada mensaje recibido desde RabbitMQ.
    Decodifica el JSON y lanza un hilo para procesar el frame.
    """
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Mensaje recibido: {data}")
        threading.Thread(target=process_message, args=(data,), daemon=True).start()
    except Exception as e:
        logger.error(f"Error en rabbitmq_message_callback: {str(e)}")

def main():
    global pool, publisher
    try:
        # Establecer el método "spawn" para el multiproceso
        mp.set_start_method("spawn", force=True)
        pool = Pool(processes=GPU_WORKERS, initializer=init_worker)

        # Iniciar el publicador (que arranca internamente su hilo)
        publisher = ExamplePublisher(AMQP_URL)
        publisher.start()

        # Iniciar el hilo que procesa la cola global de candidatos
        threading.Thread(target=candidate_queue_processor, daemon=True).start()

        # Instanciar y ejecutar el consumidor asíncrono
        consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        if publisher is not None:
            publisher.stop()
        pool.close()
        pool.join()

if __name__ == "__main__":
    logger.info("Inicio de programa")
    main()
