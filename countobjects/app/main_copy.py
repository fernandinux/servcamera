import logging
import json
import time
import threading
import cv2
import numpy as np
import redis

from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

coords_cameras = {}
logger  = configurar_logger( name   = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)
r       = redis.Redis(host  = REDIS_HOST, 
                      port  = REDIS_PORT, 
                      db    = REDIS_DB)

def obtener_indice_lapso(epoch):
    epoch = epoch / 1000
    seconds = (epoch) % 86400
    return int(epoch // 86400), int(seconds // LAPSE_TIME)

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    cam_epoch = data[DATA_EPOCH_FRAME] 
    try:
        data_old = coords_cameras.get(cam_id, {})
        if cam_epoch <=  data_old.get(DATA_EPOCH_FRAME, 0):
            logger.info(f"Frame obsoleto para cámara {cam_id}")
            return
        day,lapse_index = obtener_indice_lapso(cam_epoch)
        data["day"] = lapse_index
        data["lapse_index"] = lapse_index

        n_matchs = 0

        # Iterar sobre cada categoría y sus cajas en la nueva data
        for category, objs in data[DATA_OBJETOS_DICT].items():
            for i, new_obj in enumerate(objs):
                new_id = new_obj[DATA_OBJETO_ID_TRACKING]
                if data_old.get(DATA_OBJETOS_DICT, {}).get(category, []):
                    for obj_old in data_old[DATA_OBJETOS_DICT][category]:
                        old_id = obj_old[DATA_OBJETO_ID_TRACKING]
                        if old_id == new_id:
                            n_matchs += 1
                            break

        if n_matchs != data.get(DATA_N_OBJECTOS, 0):
            if lapse_index == data_old.get("lapse_index",None):
                data[DATA_N_OBJECTOS] = data_old.get(DATA_N_OBJECTOS, 0) + data.get(DATA_N_OBJECTOS, 0) - n_matchs
                r.hset('counted_vehicles',f'{cam_id}{day}{lapse_index}',data[DATA_N_OBJECTOS])
                logger.info(f"LOS NUEVOS OBJETOS SON {data.get(DATA_N_OBJECTOS, 0)} PARA LA CAM {data.get(DATA_CAMERA)} EN EL LAPSO {lapse_index}")

            else:
                msg= {
                    DATA_CAMERA  : data[DATA_CAMERA],
                    'lapse_index': lapse_index,
                    'count'      : data_old.get(DATA_N_OBJECTOS, 0) + data.get(DATA_N_OBJECTOS, 0) - n_matchs
                }
                thread = threading.Thread(target=publish_detection_result, args=(msg,))
                thread.start()
                data[DATA_N_OBJECTOS] = 0
        else: data[DATA_N_OBJECTOS] = data_old.get(DATA_N_OBJECTOS, 0) if lapse_index == data_old.get("lapse_index",None) else 0
        
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