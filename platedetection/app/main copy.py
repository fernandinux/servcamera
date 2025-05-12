import os
import torch.multiprocessing as mp  # type: ignore
from torch.multiprocessing import Pool, current_process  # type: ignore
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
from processor import process_plate
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
    global yolo_instance
    try:
        worker_name = current_process().name
        logger.info(f"🔄 Inicializando modelo en el worker {worker_name}...")
        yolo_instance = YOLO(YOLO_MODEL).to("cuda")
        logger.info(f"✅ Modelo cargado en el worker {worker_name}.")
    except Exception as e:
        logger.error(f"Error inicializando worker: {str(e)}")
        raise

def saveImg(frame, folder, epoch_plate):    
    output_path = folder + "plates"
    os.makedirs(output_path, exist_ok=True)
    try:
        logger.info(f"{output_path}/{epoch_plate}.jpeg")
        if not cv2.imwrite(f"{output_path}/{epoch_plate}.jpeg", frame):
            raise IOError("No se pudo guardar la imagen.")
    except IOError as e:
        logger.error(f"Error al guardar imagen: {e}")

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def get_folder_path(data):
    try: 
        day, hour = getDate(data[DATA_EPOCH_FRAME] / EPOCH_FRAME_FORMAT)
        output_path = f"/output/{data[DATA_CAMERA]}/{day}/{hour}/"
        logger.info(f"get_folder_path: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error en get folder: {str(e)}")
        return None

def load_image(path):
    img = cv2.imread(path)
    if img is None:
        logger.error(f"No se pudo abrir la imagen en la ruta: {path}")
        return None, False
    return img, True

def getResultObjects(model, frame, classes, conf, verbose=False):
    return model.predict(source=frame, classes=classes, conf=conf, verbose=verbose)

def getDevice():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Dispositivo seleccionado: {device}")
    return device

def process_image(file_path):
    """Realiza el procesamiento principal de la imagen en el worker."""
    try:
        car_image, success = load_image(file_path)
        if not success:
            return None
            
        result = process_plate(yolo_instance, car_image)
        if result is None:
            return None
        img_plate_cut, coords, success = result
        
        if not success:
            return None
        
        epoch_plate = int(time.time() * 10000)
        return (img_plate_cut, coords, epoch_plate)
        
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def process_object(folder, box):
    object_img_path = folder + "objects/" + str(box[DATA_OBJETO_EPOCH_OBJECT]) + ".jpeg"
    logger.info(f"Procesando imagen: {object_img_path}")

    result = process_image(object_img_path)
    if result is None:
        logger.warning("Warning placa no encontrada, retornando None.")
        return None, None

    img_plate_cut, coords, epoch_plate = result
    saveImg(img_plate_cut, folder, epoch_plate)
    
    logger.debug(f"Img {object_img_path} procesada.")
    return coords, epoch_plate

def process_frame(data):
    """
    Función que procesa la imagen y retorna los datos de detección.
    Se ejecuta en un proceso separado administrado por torch.multiprocessing.
    """
    try:
        folder_path = get_folder_path(data)
        logger.info(f"Carpeta de salida: {folder_path}")

        # Agregar filtro de atributos a detectar por categorías
        for cat, boxes in data[DATA_OBJETOS_DICT].items():
            for box in boxes:
                if box[DATA_OBJETO_CANDIDATO] == True:
                    coords, epoch_plate = process_object(folder_path, box)
                    
                    box[DATA_OBJETO_COORDS_ATTRIBUTE] = coords
                    box[DATA_ATRIBUTO_INIT_TIME] = epoch_plate
                    box[DATA_ATRIBUTO_STATUS] = 0
                    if coords is None or not coords:
                        box[DATA_ATRIBUTO_ID] = 1
                        box[DATA_ATRIBUTO_DESCRIPITON] = None
                        box[DATA_ATRIBUTO_ACCURACY] = None
                        box[DATA_ATRIBUTO_FINAL_TIME] = int(time.time()*1000)
                        box[DATA_ATRIBUTO_STATUS] = 0
                        
        return data
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
        
        pool.apply_async(process_frame, args=(data, ), callback=publish_detection_result)
        logger.info(f"Mensaje recibido para cámara {cam_id}: {data} Procesando")

    except Exception as e:
        logger.error(f"Error processing RabbitMQ message: {str(e)}")

def publish_detection_result(result):
    """
    Callback que se ejecuta al finalizar process_frame.
    Publica el resultado (si existe) mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando resultado de detección vía publicador asíncrono.{result}")
        if publisher is not None:
            # Se utiliza publish_async del publisher (el alias publish_data se reemplaza)
            publisher.publish_async(result)
        else:
            logger.error("Publicador no disponible para publicar el resultado.")

def main():

    global pool, publisher

    # Establecer el método "spawn" antes de crear cualquier pool
    pool = Pool(processes=GPU_WORKERS, initializer=init_worker)
    mp.set_start_method("spawn", force=True)

    # Iniciamos el publicador (internamente arranca su hilo)
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
        pool.close()
        pool.join()

if __name__ == "__main__":
    logger.info("Inicio de programa")
    main()
