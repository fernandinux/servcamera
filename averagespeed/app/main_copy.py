import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore
import redis # type: ignore

from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

coords_cameras = {}
logger = configurar_logger( name    = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)
r       = redis.Redis(host  = REDIS_HOST, 
                      port  = REDIS_PORT, 
                      db    = REDIS_DB)

def obtener_indice_lapso(epoch):
    epoch   = epoch / 1000
    seconds = (epoch) % 86400
    return int(epoch // 86400), int(seconds // LAPSE_TIME)

def mean(speed, matchs):
    return round(speed/ matchs, 4) if matchs != 0 else 0

def area(new_coords):
    new_width  = new_coords[2] - new_coords[0]
    new_height = new_coords[3] - new_coords[1]
    return new_width * new_height

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    cam_epoch = data[DATA_EPOCH_FRAME] 
    try:
        data_old = coords_cameras.get(cam_id, {})
        if data_old.get(DATA_EPOCH_FRAME) is not None:
            if cam_epoch <=  data_old.get(DATA_EPOCH_FRAME, 0):
                logger.info(f"Frame obsoleto para cámara {cam_id}")
                return
            lapse_index = obtener_indice_lapso(cam_epoch)
            day,lapse_index = obtener_indice_lapso(cam_epoch)
            data[DATA_LAPSE] = lapse_index

            sum_speed   = 0
            n_matchs    = 0
            tiempo      = (data[DATA_EPOCH_FRAME] - data_old.get(DATA_EPOCH_FRAME, 0))/1000

            # Iterar sobre cada categoría y sus cajas en la nueva data
            for category, objs in data[DATA_OBJETOS_DICT].items():
                for i, new_obj in enumerate(objs):
                    new_id = new_obj[DATA_OBJETO_ID_TRACKING]
                    new_area = area(new_obj[DATA_OBJETO_COORDENADAS])
                    if data_old.get(DATA_OBJETOS_DICT, {}).get(category, []):
                        for obj_old in data_old[DATA_OBJETOS_DICT][category]:
                            old_id = obj_old[DATA_OBJETO_ID_TRACKING]
                            if old_id == new_id:
                                old_area  = area(obj_old[DATA_OBJETO_COORDENADAS])
                                n_matchs  += 1
                                sum_speed += round((new_area-old_area)/(tiempo),4)
                                break

            if lapse_index == data_old.get(DATA_LAPSE,None):
                data['sum_speed']   = data_old.get('sum_speed', 0) + sum_speed
                data['matchs']      = data_old.get('matchs', 0) + n_matchs
                # logger.info(f"La velocidad promedio de la cámara {data[DATA_CAMERA]} es {mean(data['sum_speed'],data['matchs'])} con en el lapso {lapse_index}")
            else:
                msg= {
                    DATA_CAMERA  : data[DATA_CAMERA],
                    'lapse_index': lapse_index,
                    'speed'      : mean(data_old.get('sum_speed', 0) + sum_speed, data_old.get('matchs', 0) + n_matchs)
                }
                data['sum_speed']   = 0
                data['matchs']      = 0
                logger.info(f"La velocidad promedio de la cámara {data[DATA_CAMERA]} es {msg['speed']} con en el lapso {lapse_index}")
                thread = threading.Thread(target=publish_detection_result, args=(msg,))
                thread.start()

        coords_cameras[cam_id] = data
        return True
    
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    procesar_mensaje(body)
    # thread = threading.Thread(target=procesar_mensaje, args=(body,))
    # thread.start()

def procesar_mensaje(body):
    try:
        data = json.loads(body.decode('utf-8'))
        succes = procesamiento_coordenadas(data)
    except Exception as e:
        logger.error(f"Error processing RabbitMQ message: {str(e)}")

def publish_detection_result(result):
    if result is not None:
        # logger.info(f"Publicando resultado de detección vía publicador asíncrono: {result}")
        if publisher is not None:
            publisher.publish_async(result)
        else:
            logger.error(LOG_SEND_MSG)

def main():
    global publisher, r
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