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
logger  = configurar_logger( name   = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)
r       = redis.Redis(host  = REDIS_HOST, 
                      port  = REDIS_PORT, 
                      db    = REDIS_DB)

def vechiclesCounted(n_matchs, lapse_index, same_lapse, previous_count, current_count):
    if n_matchs != current_count:
        if lapse_index == same_lapse:
               counted  = previous_count + current_count - n_matchs
        else:  counted  = current_count - n_matchs
    else:      counted  = previous_count if lapse_index == same_lapse else 0
    return     counted 

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
        data[DATA_LAPSE] = lapse_index

        n_matchs = 0
        for category, objs in data[DATA_OBJETOS_DICT].items():
            for i, new_obj in enumerate(objs):
                new_id = new_obj[DATA_OBJETO_ID_TRACKING]
                if data_old.get(DATA_OBJETOS_DICT, {}).get(category, []):
                    for obj_old in data_old[DATA_OBJETOS_DICT][category]:
                        old_id = obj_old[DATA_OBJETO_ID_TRACKING]
                        if old_id == new_id:
                            n_matchs += 1
                            break
        
        current_count   = data.get(DATA_N_OBJECTOS, 0)
        previous_count  = data_old.get(DATA_N_OBJECTOS, 0)
        same_lapse      = data_old.get(DATA_LAPSE, None)
        if n_matchs != current_count:
            if lapse_index == same_lapse:
                data[DATA_N_OBJECTOS]   = previous_count + current_count - n_matchs
            else:
                data[DATA_N_OBJECTOS]   = current_count - n_matchs
        else: data[DATA_N_OBJECTOS]     = previous_count if lapse_index == same_lapse else 0
        logger.info(f'La cantidad para la {cam_id} en el dia {day} del lapso {lapse_index} es {data[DATA_N_OBJECTOS]}')
        
        r.hset(KEY,f'{cam_id}:{day}:{lapse_index}',data[DATA_N_OBJECTOS])
        r.sadd(f"counted_vehicles:{day}:{lapse_index}", cam_id)
        
        coords_cameras[cam_id] = data
        return True
    
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    procesar_mensaje(body)

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