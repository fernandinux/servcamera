import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore
import statistics

from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

coords_cameras = {}
logger = configurar_logger( name    = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)

def sendEnvent(epoch_object, epoch_frame, camera_id, object_id):
    alert = {
            'category'  : 1,
            'type'      : 3,
            'epoch_object'  : epoch_object,
            'epoch_frame'   : epoch_frame,
            'camera_id' : camera_id,
            'object_id' : object_id,
            'message'   : 'Congestion vehicular'
            }
    thread = threading.Thread(target=publish_detection_result, args=(alert,))
    thread.start()  

def compareResults(mean, deviation, value):
    if value < mean - deviation:
        logger.info("Congestión detectada")
        return True
    elif value > mean + deviation:
        logger.info("Flujo más rápido de lo normal")
        return False
    return False

def getStatistics(values):
    return np.nanmean(values), np.nanstd(values)

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    lapse_time = data['lapse_index']
    try:
        history_data = coords_cameras.get(cam_id, np.full((144, 2, 7), np.nan)) 
        if data.get('speed') is not None:
            values = history_data[lapse_time][0]
            mean, deviation = getStatistics(values)
            logger.info(f"Values to {cam_id} in speed in lapse {lapse_time} are {values} if speed is {data['speed']}")
            if compareResults(mean, deviation, data['speed']):
                sendEnvent(data[DATA_OBJETO_EPOCH_OBJECT], data[DATA_EPOCH_FRAME], cam_id, data[DATA_OBJETO_ID_CONCATENADO])
            history_data[lapse_time][0] = np.append(values[1:7], data['speed'])

        elif data.get('count') is not None:
            values = history_data[lapse_time][1]
            mean, deviation = getStatistics(values)
            logger.info(f"Values to {cam_id} in count in lapse {lapse_time} are {values}")
            if compareResults(mean, deviation, data['count']):
                sendEnvent(data[DATA_OBJETO_EPOCH_OBJECT], data[DATA_EPOCH_FRAME], cam_id, data[DATA_OBJETO_ID_CONCATENADO])
            history_data[lapse_time][1] = np.append(values[1:7], data['count'])
        else:
            logger.warning('These message havent the corrects items for this service')

        coords_cameras[cam_id] = history_data
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