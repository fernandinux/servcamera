import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore
import redis # type: ignore
import math

from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

coords_cameras = {}
logger  =configurar_logger( name    = FILE_NAME_LOG,
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
    return round(speed/ matchs, 1) if matchs != 0 else 0

def getArea(new_coords):
    new_width  = new_coords[2] - new_coords[0]
    new_height = new_coords[3] - new_coords[1]
    return new_width * new_height

def getCenters(bbox):
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2

def sendEvent(cam, epoch_frame, obj, speed):
    alert = {
            'category'    : 0,
            'type'        : 10,
            'message'     : f'{speed}',
            'object_id'   : obj[DATA_OBJETO_ID_CONCATENADO],
            'epoch_object': obj[DATA_OBJETO_EPOCH_OBJECT],
            'epoch_frame' : epoch_frame,
            'camera_id'   : cam,
            'id_tracking' : obj[DATA_OBJETO_ID_TRACKING],
            }
    
    logger.info(alert)
    thread = threading.Thread(target=publish_detection_result, args=(alert,))
    thread.start()  

def rotation_matrix(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = np.radians(yaw_deg)
    pitch = np.radians(pitch_deg)
    # Rotación pitch (inclinación) alrededor del eje X
    R_pitch = np.array([
        [1,           0,            0],
        [0,  np.cos(pitch), -np.sin(pitch)],
        [0,  np.sin(pitch),  np.cos(pitch)]
    ])
    # Rotación yaw (rotación en planta) alrededor del eje Z
    R_yaw = np.array([
        [ np.cos(yaw), -np.sin(yaw), 0],
        [ np.sin(yaw),  np.cos(yaw), 0],
        [          0,           0,   1]
    ])
    # Primero pitch, luego yaw
    return R_yaw @ R_pitch

def pixel_to_world(u: float, v: float,
                   f_x: float, f_y: float,
                   c_x: float, c_y: float,
                   cam_height: float,
                   yaw_deg: float, pitch_deg: float) -> np.ndarray:

    x_cam = (u - c_x) / f_x
    y_cam = (v - c_y) / f_y
    d_cam = np.array([x_cam, y_cam, 1.0])
    d_cam /= np.linalg.norm(d_cam)
    R = rotation_matrix(yaw_deg, pitch_deg)
    d_world = R @ d_cam

    # Cámara en (0, 0, cam_height), buscar t tal que z=0
    t = -cam_height / d_world[2]
    P = np.array([0.0, 0.0, cam_height]) + t * d_world
    return P[:2]

def getFxFy(fov_h_deg, fov_v_deg, img_w, img_h):
    f_x = img_w / (2 * np.tan(np.radians(fov_h_deg) / 2))
    f_y = img_h / (2 * np.tan(np.radians(fov_v_deg) / 2))
    c_x, c_y = img_w / 2, img_h / 2
    return f_x, f_y, c_x, c_y

def velocity_from_bboxes(bbox1, bbox2, dt: float,
                         img_w = 1920, img_h = 1080, parameters = {}
                         ):
    
    fov_h_deg  = parameters.get(DATA_FOV_H      , FOV_H_DEG) 
    fov_v_deg  = parameters.get(DATA_FOV_V      , FOV_V_DEG) 
    cam_height = parameters.get(DATA_CAM_HEIGHT , CAM_HEIGHT)
    yaw_deg    = parameters.get(DATA_ROTATION   , ROTATION) 
    pitch_deg  = parameters.get(DATA_INCLINATION, INCLINATION)

    f_x, f_y, c_x, c_y = getFxFy(fov_h_deg, fov_v_deg, img_w, img_h)
    points = []
    for box in [bbox1, bbox2]:
        x, y = box
        P = pixel_to_world(x, y, f_x, f_y, c_x, c_y, cam_height, yaw_deg, pitch_deg)
        points.append(P)

    dist = np.linalg.norm(points[1] - points[0])
    return round(dist * KMH / dt, 1)

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    cam_epoch = data[DATA_EPOCH_FRAME] 
    try:
        data_old = coords_cameras.get(cam_id, {})
        if data_old.get(DATA_EPOCH_FRAME) is not None:
            if cam_epoch <=  data_old.get(DATA_EPOCH_FRAME, 0):
                logger.info(f"Frame obsoleto para cámara {cam_id}")
                return
            
            parameters = json.loads(r.hget(KEY,cam_id))
            # if parameters != data_old.get('parameters', None) : 
            #     r_matrix   = rotation_matrix(parameters['rotation'],parameters['inclination'])
            #     logger.info(f'{parameters}')

            img_w = data[DATA_SHAPE][1]
            img_h = data[DATA_SHAPE][0]

            lapse_index = obtener_indice_lapso(cam_epoch)
            day,lapse_index = obtener_indice_lapso(cam_epoch)
            data[DATA_LAPSE] = lapse_index
            data['parameters'] = parameters

            sum_speed   = 0
            n_matchs    = 0
            tiempo      = (data[DATA_EPOCH_FRAME] - data_old.get(DATA_EPOCH_FRAME, 0))/1000

            # Iterar sobre cada categoría y sus cajas en la nueva data
            for category, objs in data[DATA_OBJETOS_DICT].items():
                for i, new_obj in enumerate(objs):
                    new_id = new_obj[DATA_OBJETO_ID_TRACKING]
                    x1c, y1c = getCenters(new_obj[DATA_OBJETO_COORDENADAS])
                    if data_old.get(DATA_OBJETOS_DICT, {}).get(category, []):
                        for obj_old in data_old[DATA_OBJETOS_DICT][category]:
                            old_id = obj_old[DATA_OBJETO_ID_TRACKING]
                            if old_id == new_id:
                                x2c, y2c = getCenters(obj_old[DATA_OBJETO_COORDENADAS])
                                n_matchs  += 1
                                myspeed = velocity_from_bboxes((x1c, y1c), (x2c, y2c), tiempo, img_w, img_h, parameters) #(new_area-old_area)/(tiempo) 
                                if myspeed > parameters.get(DATA_LIMIT_SPEED,LIMIT_SPEED): 
                                    sendEvent(cam_id, cam_epoch, new_obj, myspeed)
                                    logger.info(f'la velocidad es {myspeed} in {cam_id}')
                                sum_speed += round(myspeed,1)
                                break

            same_lapse      = data_old.get(DATA_LAPSE, None)
            if lapse_index == same_lapse:
                data[DATA_SUM_SPEED] = data_old.get(DATA_SUM_SPEED, 0) + sum_speed
                data[DATA_MATCHS]    = data_old.get(DATA_MATCHS, 0) + n_matchs
                speed                = mean(data[DATA_SUM_SPEED] , data[DATA_MATCHS])
            else:
                data[DATA_SUM_SPEED]= sum_speed
                data[DATA_MATCHS]      = n_matchs
                speed               = mean(sum_speed, n_matchs)
            r.hset(KEY,f'{cam_id}:{day}:{lapse_index}', float(speed))
            r.sadd(f"{KEY}:{day}:{lapse_index}", cam_id)
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