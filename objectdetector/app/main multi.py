import os
import torch.multiprocessing as mp  # type: ignore
from torch.multiprocessing import Pool, current_process  # type: ignore
import threading
import torch  # type: ignore
import json
import cv2  # type: ignore
import time
from datetime import datetime
from ultralytics import YOLO  # type: ignore
import logging
import queue

# Importamos la configuración y la función de logging
from config import *
from config_logger import configurar_logger
# Importamos el consumer y el publicador (ya definidos en otros módulos)
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración global
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 
yolo_instance = None
pool = None

# Definimos el tamaño máximo de la cola (puede definirse en config si se prefiere)
MAX_QUEUE_SIZE = 50
# Cola para almacenar los arrays de imagen junto con sus datos (cola acotada)
image_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
# Creamos un objeto evento para notificar cuando se añade un elemento a la cola
image_event = threading.Event()

def init_worker():
    """
    Inicializa el modelo YOLO y el publicador en cada proceso worker.
    """
    global yolo_instance, publisher_instance
    try:
        worker_name = current_process().name
        logger.info(f"🔄 Inicializando modelo en el worker {worker_name}...")
        yolo_instance = YOLO(YOLO_MODEL).to("cuda")
        
        publisher_instance = ExamplePublisher(AMQP_URL)
        publisher_instance.start()
        
        logger.info(f"✅ Modelo cargado en el worker {worker_name}.")
    except Exception as e:
        logger.error(f"Error inicializando worker: {str(e)}")
        raise

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def getPath(data):
    day, hour = getDate(data[DATA_EPOCH_FRAME] / EPOCH_FRAME_FORMAT)
    output_path = f"/output/{data[DATA_CAMERA]}/{day}/{hour}/frames/{data[DATA_EPOCH_FRAME]}.jpeg"
    logger.info(f"Ruta generada: {output_path}")
    return output_path

def getCategories(class_dict, selected_categories=None):
    if selected_categories is None:
        selected_categories = ["vehicles"]
    # Filtra las categorías seleccionadas y agrega la lista "total"
    def getCategoriesSelected(cd, sel):
        return {cat: cd[cat] for cat in sel if cat in cd}
    cat_sel = getCategoriesSelected(class_dict, selected_categories)
    cat_sel['total'] = [cls for sub in cat_sel.values() for cls in sub]
    return cat_sel

def detect_objects(img, classes, data):
    """
    Función que procesa la imagen y retorna los datos de detección.
    Se ejecuta en un proceso del pool (multiproceso).
    """
    try:
        inicio_tiempo = time.time()
        if img is None:
            logger.error("Imagen nula recibida en detect_objects.")
            return None
        
        data[DATA_INIT_TIME] = int(time.time() * 1000)
        results_yolo = yolo_instance.predict(source=img, classes=classes['total'], conf=CONF, verbose=False)
        logger.info(f"Tiempo de inferencia: {time.time() - data[DATA_INIT_TIME]/1000:.3f} s para imagen {data[DATA_EPOCH_FRAME]}")
        
        data[DATA_N_OBJECTOS] = len(results_yolo[0].boxes)
        objects_data_list = {}
        for box in results_yolo[0].boxes:
            cat = int(box.cls[0] + 1)
            if cat not in objects_data_list:
                objects_data_list[cat] = []
            objects_data_list[cat].append({
                DATA_OBJETO_COORDENADAS: list(map(int, box.xyxy[0])),
                DATA_OBJETO_PRECISION: int(box.conf[0].item() * 100),
                DATA_OBJETO_EPOCH_OBJECT: int(time.time() * EPOCH_OBJECT_FORMAT)
            })
        data[DATA_OBJETOS_DICT] = objects_data_list
        data[DATA_STATUS_FRAME] = True
        data[DATA_FINAL_TIME] = int(time.time() * 1000)

        logger.debug(f"Imagen procesada: {len(objects_data_list)} objetos detectados.")
        logger.info(f"Publicando resultado: {data}")
        publisher_instance.publish_async(data)
        return True
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def process_message(data):
    """
    A partir de los datos JSON, obtiene la ruta de la imagen, la abre con cv2.imread y almacena el array junto con los datos en la cola.
    Se limita la cantidad de arrays almacenados usando una cola acotada.
    """
    try:
        file_path = getPath(data)
        inicio_tiempo = time.time()
        img = cv2.imread(file_path)
        logger.info(f"Lectura img {time.time()-inicio_tiempo} imagen en: {file_path}")
        if img is None:
            logger.error(f"No se pudo cargar la imagen en la ruta: {file_path}")
            return
        
        if image_queue.full():
            logger.warning(f"La cola está llena (máximo {MAX_QUEUE_SIZE} elementos). Se descarta la imagen: {file_path}")
            return
        
        image_queue.put((img, data))
        logger.info(f"Imagen cargada y almacenada en la cola. Tamaño actual: {image_queue.qsize()}/{MAX_QUEUE_SIZE}")
        # Notifica que hay un nuevo elemento en la cola
        image_event.set()
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    """
    Callback para cada mensaje recibido desde RabbitMQ.
    Decodifica el JSON y lanza un hilo para obtener la imagen.
    """
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Datos recibidos: {data}")
        candidate = data[DATA_CANDIDATO]
        if candidate == 1:
            # Procesar en un hilo para obtener la imagen y almacenarla en la cola.
            threading.Thread(target=process_message, args=(data,), daemon=True).start()
            logger.info(f"Mensaje procesado para cámara {data[DATA_CAMERA]}")
        else:
            logger.info(f"Mensaje recibido para cámara {data[DATA_CAMERA]} sin procesamiento.")
    except Exception as e:
        logger.error(f"Error en el callback del mensaje RabbitMQ: {str(e)}")

def queue_processor():
    """
    Hilo que espera a que se agregue un elemento a la cola mediante un evento,
    y luego extrae todos los elementos para enviarlos a los workers (multiproceso)
    para ejecutar yolo.predict.
    """
    while True:
        # Espera hasta que el evento se active (bloquea aquí)
        image_event.wait()
        try:
            # Procesa todos los elementos disponibles en la cola
            while not image_queue.empty():
                img, data = image_queue.get_nowait()
                classes = getCategories(CLASS_DICT)
                pool.apply_async(detect_objects, args=(img, classes, data))
                logger.info(f"Imagen enviada a los workers para detección. Cola actual: {image_queue.qsize()}/{MAX_QUEUE_SIZE}")
                image_queue.task_done()
        except queue.Empty:
            pass
        # Una vez procesados todos los elementos, se limpia el evento para esperar la próxima señal
        image_event.clear()

def main(test_mode=False):
    global pool

    # Establecer el método "spawn" para el multiproceso
    mp.set_start_method("spawn", force=True)
    pool = Pool(processes=GPU_WORKERS, initializer=init_worker)

    # Inicia el procesamiento de la cola en un hilo separado (basado en evento)
    threading.Thread(target=queue_processor, daemon=True).start()

    # Instancia y ejecución del consumidor asíncrono (ya definido en consumer.py)
    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        pool.close()
        pool.join()

if __name__ == "__main__":
    logger.info("Inicio de programa")
    main()
