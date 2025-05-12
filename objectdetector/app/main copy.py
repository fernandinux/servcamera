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

# Importamos la configuración y la función de logging
from config import *
from config_logger import configurar_logger
# Importamos el consumer modificado
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración global
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 
yolo_instance = None
pool = None

def init_worker():
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
    logger.info(f"getPath: {output_path}")
    return output_path

def load_image(path):
    img = cv2.imread(path)
    if img is None:
        logger.error(f"No se pudo cargar la imagen en la ruta: {path}")
        return None, False
    return img, True

def getResultObjects(model, frame, classes, conf, verbose=False):
    return model.predict(source=frame, classes=classes, conf=conf, verbose=verbose)

def getDevice():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Dispositivo seleccionado: {device}")
    return device

def getCategories(class_dict, selected_categories=None):
    if selected_categories is None:
        selected_categories = ["vehicles"]
    # Filtra las categorías seleccionadas y agrega la lista "total"
    def getCategoriesSelected(cd, sel):
        return {cat: cd[cat] for cat in sel if cat in cd}
    cat_sel = getCategoriesSelected(class_dict, selected_categories)
    cat_sel['total'] = [cls for sub in cat_sel.values() for cls in sub]
    return cat_sel

def detect_objects(file_path, classes, data):
    """
    Función que procesa la imagen y retorna los datos de detección.
    Se ejecuta en un proceso separado administrado por torch.multiprocessing.
    """
    try:
        inicio_tiempo = time.time()
        img, success = load_image(file_path)
        if not success:
            return None
        elapsed_tiempo = time.time() - inicio_tiempo
        logger.info(f"Tiempo de lectura de la imagen {elapsed_tiempo}")
        
        data[DATA_INIT_TIME] = int(time.time() * 1000)
        results_yolo = getResultObjects(yolo_instance, img, classes=classes['total'], conf=CONF)
        logger.info(f"Tiempo: {time.time()-data[DATA_INIT_TIME]/1000}")
        data[DATA_N_OBJECTOS] = len(results_yolo[0].boxes)
        objects_data_list = {}
        for box in results_yolo[0].boxes:
            cat = int(box.cls[0] + 1)
            if cat not in objects_data_list:
                objects_data_list[cat] = []
            
            objects_data_list[cat].append({
                DATA_OBJETO_COORDENADAS: list(map(int, box.xyxy[0])),
                DATA_OBJETO_PRECISION: int(box.conf[0].item() * 100),
                DATA_OBJETO_EPOCH_OBJECT:int(time.time()*EPOCH_OBJECT_FORMAT)
            })
        data[DATA_OBJETOS_DICT] = objects_data_list
        data[DATA_STATUS_FRAME] = True

        data[DATA_FINAL_TIME] = int(time.time() * 1000)

        logger.debug(f"Img {file_path}: {len(objects_data_list)} objetos detectados.")
        
        logger.info(f"Publicando {data}")
        publisher_instance.publish_async(data)
        return True
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    """
    Callback para cada mensaje recibido desde RabbitMQ.
    Se decodifica el JSON, se calcula la ruta de la imagen y se despacha
    la función de procesamiento al pool de workers.
    """
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Datos recibidos: {data}")
        cam_id = data[DATA_CAMERA]
        candidate = data[DATA_CANDIDATO]
        file_path = getPath(data)
        classes = getCategories(CLASS_DICT)
        
        if candidate == 1:
            pool.apply_async(detect_objects, args=(file_path, classes, data))
            logger.info(f"Mensaje recibido para cámara {cam_id}: {data} Procesando")
        else: 
            logger.info(f"Mensaje recibido para cámara {cam_id}: {data} NO Procesando")
    except Exception as e:
        logger.error(f"Error processing RabbitMQ message: {str(e)}")

def publish_detection_result(result):
    """
    Callback que se ejecuta al finalizar detect_objects.
    Publica el resultado (si existe) mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando resultado de detección vía publicador asíncrono.{result}")
        if publisher_instance is not None:
            # Se utiliza publish_async del publisher (el alias publish_data se reemplaza)
            logger.info(f"Publicando {result}")
            publisher_instance.publish_async(result)
        else:
            logger.error("Publicador no disponible para publicar el resultado.")

def simulate_test_queue(test_folder):
    """
    Función para simular la cola de mensajes leyendo imágenes de una carpeta.
    Cada imagen se procesa como si fuera un mensaje recibido.
    """
    if not os.path.isdir(test_folder):
        logger.error(f"La carpeta de test no existe: {test_folder}")
        return
    # Extraer los nombres numéricos de los archivos
    image_names = [int(f[:-5]) for f in os.listdir(test_folder) 
                if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # Ordenar los nombres numéricos de menor a mayor
    image_names = sorted(image_names)

    # Para obtener también la lista de archivos ordenados según el nombre numérico:
    image_files = sorted(
        [os.path.join(test_folder, f) for f in os.listdir(test_folder) 
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))],
        key=lambda x: int(os.path.basename(x)[:-5])
    )
    if not image_files:
        logger.warning(f"No se encontraron imágenes en: {test_folder}")
        return

    for i, image_file in enumerate(image_files):
        # Simulamos un mensaje con datos mínimos requeridos.
        data = {
            DATA_CAMERA: "test_camera",                     # str
            DATA_EPOCH_FRAME: image_names[i],                # int
            DATA_FUNCIONALIDAD: "vehicles",                 # str
            DATA_CANDIDATO: True,                           # bool
            DATA_STATUS_FRAME: False                        # bool
        }
        logger.info(f"Simulando mensaje para la imagen: {image_file}")
        pool.apply_async(detect_objects, args=(image_file, getCategories(CLASS_DICT), data), callback=publish_detection_result)
        time.sleep(0.1)  # Simula un intervalo entre mensajes

def main(test_mode=False):
    """
    Función principal.
    
    Parámetro:
      test_mode (bool): Si es True, se simula una cola leyendo imágenes de una carpeta.
                        Si es False, se inicia el consumer de RabbitMQ.
    """
    global pool

    # Establecer el método "spawn" antes de crear cualquier pool
    mp.set_start_method("spawn", force=True)
    pool = Pool(processes=GPU_WORKERS, initializer=init_worker)

    # Iniciamos el publicador (internamente arranca su hilo)
    # publisher = ExamplePublisher(AMQP_URL)
    # publisher.start()

    if test_mode:
        # Ruta de la carpeta con imágenes de test (modifica esta ruta según tu entorno)
        init_time = time.time()
        test_folder = "/app/frames"
        logger.info("Modo test activado. Simulando cola de imágenes.")
        simulate_test_queue(test_folder)
        pool.close()
        pool.join()
        logger.info(f"Tiempo de procesamiento: {time.time()-init_time} segundos")
    else:
        consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
        try:
            logger.info("Iniciando consumer RabbitMQ...")
            consumer.run()
        except KeyboardInterrupt:
            logger.info("Interrupción por teclado. Cerrando...")
        finally:
            # publisher.stop()
            pool.close()
            pool.join()

if __name__ == "__main__":
    logger.info("Inicio de programa")
    test_mode = os.environ.get("TEST_MODE", "false").lower() in ("1", "true", "yes")
    main(test_mode)
