import os
import json
import time
import threading
import queue
from datetime import datetime

import cv2  # type: ignore
import numpy as np  # type: ignore
import redis  # type: ignore
import torch  # type: ignore
import torch.multiprocessing as mp  # type: ignore
from torch.multiprocessing import Pool, current_process  # type: ignore
from ultralytics import YOLO  # type: ignore

import logging

# Importamos la configuración, el consumer y el publicador
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración Logger\logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Instancias globales (serán sobreescritas en init_worker)
yolo_instance = None
publisher_instance = None
metrics = None  # Se inicializa en main bajo guardia

# Cola global para almacenar imágenes
image_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)

# Pool de conexiones global para Redis
redis_pool = redis.ConnectionPool(host=REDIS_HOST_IMAGES, port=REDIS_PORT_IMAGES, db=REDIS_DB, socket_timeout=REDIS_TIMEOUT)
# redis_pool_parameters = redis.ConnectionPool(
#     host=REDIS_HOST_PARAMETERS, port=REDIS_PORT_PARAMETERS, db=REDIS_DB,
#     socket_timeout=REDIS_TIMEOUT, decode_responses=True
# )

# Umbral para log de métricas
LOG_METRIC_INTERVAL = 100


def log_metrics():
    """Calcula y registra las tasas de consumo, procesamiento y publicación."""
    elapsed = time.time() - metrics['start_time']
    if elapsed <= 0:
        return
    consume_rate = metrics['messages_consumed'] / elapsed
    candidates_rate = metrics['messages_candidates'] / elapsed
    process_rate = metrics['messages_processed'] / elapsed
    publish_rate = metrics['messages_published'] / elapsed
    logger.warning(
        f"[METRICS] Consumidos={metrics['messages_consumed']} ({consume_rate:.2f} msg/s), "
        f"Candidatos={metrics['messages_candidates']} ({candidates_rate:.2f} msg/s), "
        f"Procesados={metrics['messages_processed']} ({process_rate:.2f} msg/s), "
        f"Publicados={metrics['messages_published']} ({publish_rate:.2f} msg/s)"
    )


def init_worker(shared_metrics):
    """Inicializa el modelo y publisher en cada worker, compartiendo métricas."""
    global yolo_instance, publisher_instance, metrics
    metrics = shared_metrics
    worker_name = current_process().name
    logger.info(f"🔄 Inicializando modelo en el worker {worker_name}...")
    yolo_instance = YOLO(YOLO_MODEL).to('cuda')
    publisher_instance = ExamplePublisher(AMQP_URL)
    publisher_instance.start()
    logger.info(f"✅ Modelo cargado en el worker {worker_name}.")


def getCategories(class_dict, selected_categories=('vehicles',)):
    cat_sel = {cat: class_dict.get(cat, []) for cat in selected_categories}
    cat_sel['total'] = [cls for sub in cat_sel.values() for cls in sub]
    return cat_sel


def getResultObjects(model, frame, classes, conf, verbose=False):
    return model.predict(source=frame, classes=classes, conf=conf, verbose=verbose)


def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime(FILE_DATE), dt.strftime(FILE_HOUR)


def detect_objects_from_image(img, classes, data):
    """Procesa la imagen, detecta objetos y publica, actualizando métricas."""
    try:
        # Marcar inicio de procesamiento
        timestamp = int(time.time() * EPOCH_FORMAT)
        data[DATA_INIT_TIME] = timestamp

        # Detección YOLO
        # mytime = time.time()
        results_yolo = getResultObjects(yolo_instance, img, classes=classes['total'], conf=CONF)
        # logger.warning(f'predict time is {time.time()-mytime}')
        data[DATA_N_OBJECTOS] = len(results_yolo[0].boxes)

        # Empaquetar datos de objetos
        objects_data_list = {}
        for box in results_yolo[0].boxes:
            cat = int(box.cls[0] + 1)
            objects_data_list.setdefault(cat, []).append({
                DATA_OBJETO_COORDENADAS: list(map(int, box.xyxy[0])),
                DATA_OBJETO_PRECISION: int(box.conf[0].item() * 100),
                DATA_OBJETO_EPOCH_OBJECT: int(time.time() * EPOCH_OBJECT_FORMAT)
            })
        data[DATA_OBJETOS_DICT] = objects_data_list
        data[DATA_STATUS_FRAME] = True
        data[DATA_FINAL_TIME] = int(time.time() * EPOCH_FORMAT)

        # Incrementar métricas
        metrics['messages_processed'] += 1
        logger.debug(
            f"Imagen {data.get(DATA_EPOCH_FRAME, 'unknown')}: "
            f"{sum(len(v) for v in objects_data_list.values())} objetos detectados.")

        # Publicar y contabilizar
        publisher_instance.publish_async(data)
        metrics['messages_published'] += 1
        return True
    except Exception:
        logger.exception("Error en procesamiento de imagen")
        return None


def read_image_and_enqueue(data):
    try:
        r = redis.Redis(connection_pool=redis_pool)
        # params = redis.Redis(connection_pool=redis_pool_parameters)
        # extra = params.hgetall(data[DATA_CAMERA])
        # if extra:
        #     data['zone_restricted'] = {k: json.loads(v) for k, v in extra.items()}

        image_bytes = r.get(f"{data[DATA_CAMERA]}{data[DATA_EPOCH_FRAME]}")
        if not image_bytes:
            logger.error(f"Frame {data[DATA_EPOCH_FRAME]} no existe en Redis")
            return

        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("Formato de imagen inválido")
            return

        if image_queue.full():
            logger.warning(f"La cola está llena. Tamaño: {image_queue.qsize()}")
            return

        image_queue.put((img, data))
        logger.info(f"Imagen encolada. Tamaño cola: {image_queue.qsize()}/{MAX_QUEUE_SIZE}")
    except Exception:
        logger.exception("Error al abrir imagen")


def process_image_queue():
    while True:
        img, data = image_queue.get()
        classes = getCategories(CLASS_DICT)
        logger.info("Despachando imagen para procesamiento YOLO")
        pool.apply_async(detect_objects_from_image, args=(img, classes, data))
        image_queue.task_done()


def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    data = json.loads(body.decode('utf-8'))
    # Incrementar consumidos
    metrics['messages_consumed'] += 1
    # Log de métricas periódicas
    if metrics['messages_consumed'] % LOG_METRIC_INTERVAL == 0:
        log_metrics()
    logger.info(f"Datos recibidos: {data}")
    if data.get(DATA_CANDIDATO) == 1:
        metrics['messages_candidates'] += 1
        threading.Thread(target=read_image_and_enqueue, args=(data,), daemon=True).start()
    else:
        logger.info("No es frame candidato, descartado.")


def main():
    global pool, metrics
    mp.set_start_method('spawn', force=True)

    # Crear manager y métricas dentro de guardia principal
    manager = mp.Manager()
    metrics = manager.dict({
        'messages_consumed': 0,
        'messages_candidates':0,
        'messages_processed': 0,
        'messages_published': 0,
        'start_time': time.time()
    })

    # Inicializar pool con métricas compartidas
    pool = Pool(
        processes=GPU_WORKERS,
        initializer=init_worker,
        initargs=(metrics,)
    )

    # Lanzar thread de procesamiento de cola
    threading.Thread(target=process_image_queue, daemon=True).start()

    # Iniciar consumidor
    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        pool.close()
        pool.join()
        if publisher_instance:
            publisher_instance.stop()
        logger.info("Cierre completo.")


if __name__ == '__main__':
    logger.info("Inicio de programa")
    main()
