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
logger2 = configurar_logger(name="pruebas", log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 
coords_cameras = {}

def getPath(epoch, camera_id):
    day, hour = getDate(epoch / EPOCH_FRAME_FORMAT)
    output_path = f"/output/{camera_id}/{day}/{hour}/frames/{epoch}.jpeg"
    logger.info(f"getPath: {output_path}")
    return output_path

def load_image(path):
    img = cv2.imread(path)
    if img is None:
        logger.error(f"No se pudo cargar la imagen en la ruta: {path}")
        return None, False
    return img, True

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%d-%m'), dt.strftime('%H')

def saveImg(frame, epoch_frame, epoch_object, camera_id):    
    day, hour = getDate(epoch_frame/EPOCH_FRAME_FORMAT)
    output_path = f"/output/{camera_id}/{day}/{hour}/objects"

    os.makedirs(output_path, exist_ok=True)

    try:
        if not cv2.imwrite(f"{output_path}/{epoch_object}.jpeg",frame):
            raise IOError("No se pudo guardar la imagen.")
    except IOError as e:
        logger.error(f"Error al guardar imagen: {e}")

def is_inside(new_coords, old_coords):
    """Retorna True si new_coords está dentro de old_coords."""
    x1, y1, x2, y2 = new_coords
    x1_old, y1_old, x2_old, y2_old = old_coords
    return (x1_old <= x1 <= x2_old and y1_old <= y1 <= y2_old and
            x1_old <= x2 <= x2_old and y1_old <= y2 <= y2_old)

def expand_bbox(coords, padding=PADDING):
    """Expande las coordenadas del bounding box en 'padding' píxeles."""
    x1, y1, x2, y2 = coords
    return [x1 - padding, y1 - padding, x2 + padding, y2 + padding]

def guardar_objectos(camera_id, data):
    epoch_frame = data[DATA_EPOCH_FRAME]
    file_path = getPath(epoch_frame, camera_id)

    img, success = load_image(file_path)
    if not success:
        return None
    
    for categoria, boxes in data[DATA_OBJESTOS_LIST].items():
        for box in boxes:
            if box[DATA_OBJETO_CANDIDATO] == True:
                coords = box[DATA_OBJETO_COORDENADAS]
                img_slicing = img[coords[1]:coords[3], coords[0]:coords[2]]
                saveImg(img_slicing, epoch_frame, box[DATA_OBJETO_EPOCH_OBJECT],camera_id)

def procesamiento_coordenadas(data):
    """
    Procesa las coordenadas de detecciones para una cámara determinada.
    Se comparan las coordenadas actuales con las anteriores y se actualiza
    la detección según la mayor confianza.
    """
    cam_id = data[DATA_CAMERA]
    # Se asume que DATA_OBJESTOS_LIST es una lista de diccionarios de detección
    
    data_actual = coords_cameras.get(cam_id, {})

    logger2.info(f"Coords actuales: {data_actual} para camara {cam_id}")
    logger2.info(f"Lista de Objetos : {data[DATA_OBJESTOS_LIST]}")

    try:
        # Iterar sobre cada categoría y sus cajas en la nueva data
        for categoria, new_boxes in data[DATA_OBJESTOS_LIST].items():
            logger2.info("1")
            for new_box in new_boxes:
                new_conf = new_box[DATA_OBJETO_PRECISION]
                new_coords = new_box[DATA_OBJETO_COORDENADAS]
                logger2.info("2")
                
                # Bandera para indicar si se encontró coincidencia con la data anterior
                match_found = False

                new_box[DATA_OBJETO_STATUS] = False
                new_box[DATA_OBJETO_CANDIDATO] = True

                # Si la categoría existe en la data anterior, comparo cada box
                logger2.info("3")
                if categoria in data_actual[DATA_OBJESTOS_LIST]:
                    for old_box in data_actual[DATA_OBJESTOS_LIST][categoria]:
                        logger2.info("4")
                        old_coords = old_box[DATA_OBJETO_COORDENADAS]
                        if is_inside(new_coords, expand_bbox(old_coords)):
                            logger2.info("Match----------------------------------------------------")
                            # Comparar precisión: si la nueva es mayor, se desmarca el candidato anterior
                            if new_conf > old_box[DATA_OBJETO_PRECISION]:
                                old_box[DATA_OBJETO_CANDIDATO] = False
                            else:
                                new_box[DATA_OBJETO_CANDIDATO] = False

                            match_found = True
                            break
        
        # logger2.info(f"Data Procesada: {data_actual}")
        logger2.info(f"Data actual procesada: {data_actual} para camara {cam_id}")
        guardar_objectos(cam_id, data_actual)
        publish_detection_result(data_actual)
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
    """
    Callback para cada mensaje recibido desde RabbitMQ.
    Se decodifica el JSON, se procesa la información y se publica el resultado.
    """
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Datos recibidos: {data}")
        # imprimir_tipos(data)
                       
        # Se procesa la información y se publica el resultado
        succes = procesamiento_coordenadas(data)
        
        logger.info(f"Mensaje recibido para cámara {data[DATA_CAMERA]}: {data} Procesando")
    
    except Exception as e:
        logger.error(f"Error processing RabbitMQ message: {str(e)}")

def publish_detection_result(result):
    """
    Callback que se ejecuta al finalizar el procesamiento de detecciones.
    Publica el resultado (si existe) mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando resultado de detección vía publicador asíncrono: {result}")
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