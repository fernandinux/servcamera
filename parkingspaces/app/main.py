import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore
import redis # type: ignore


from datetime import datetime
from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

coords_cameras = {}
object_tracker = {}

logger = configurar_logger( name    = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)

r       = redis.Redis(host  = REDIS_HOST, 
                      port  = REDIS_PORT, 
                      db    = REDIS_DB)


def drawVechicles(new_data, name, zone):
    imagen = np.ones((1080, 1920, 3), dtype=np.uint8) * 255
    pts = np.array(zone, np.int32)
    pts = pts.reshape((-1, 1, 2))
    for draw_data in new_data:
        bbox = draw_data[DATA_OBJETO_COORDENADAS]
        cv2.rectangle(imagen, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
    cv2.polylines(imagen, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
    cv2.imwrite(f'/output/{name}.jpg', imagen)

def is_inside(new_coords, old_coords):
    """Retorna True si new_coords está dentro de old_coords."""
    x1, y1, x2, y2 = new_coords
    x1_old, y1_old, x2_old, y2_old = old_coords
    return (x1_old <= x1 <= x2_old and y1_old <= y1 <= y2_old and
            x1_old <= x2 <= x2_old and y1_old <= y2 <= y2_old)

def expand_bbox(coords, padding=PADDING):
    """Expande las coordenadas del bounding box en 'padding' píxeles."""
    x1, y1, x2, y2 = coords
    alto = y2-y1
    ancho = x2-x1
    return [x1 - int(padding*ancho), y1 - int(padding*alto), x2 + int(padding*ancho), y2 + int(padding*alto)]

def sendEvent(epoch_object, epoch_frame, camera_id, object_id, tracking_id, zone, message = '', category = CAT_NOTIFICACION):
    alert = {
             EVENT_CATEGORY     : category,
             EVENT_TYPE         : TYPE_PARKING if zone == CATEGORY_PARKING else TYPE_RESTRICTED,
             EVENT_EPOCH_OBJECT : epoch_object,
             EVENT_EPOCH_FRAME  : epoch_frame,
             EVENT_CAMERA_ID    : camera_id,
             EVENT_OBJECT_ID    : object_id,
             EVENT_TRACKING     : tracking_id, 
             EVENT_MESSAGE      : message,
             EVENT_ID_ZONE      : TYPE_PARKING if zone == CATEGORY_PARKING else zone
            }
    thread = threading.Thread(target=publish_detection_result, args=(alert,))
    thread.start()    

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    epoch = data[DATA_EPOCH_FRAME]
    try:
        data_old  = coords_cameras.get(cam_id, {})
        if epoch <= data_old.get(DATA_EPOCH_FRAME, 0):
            logger.info(f"Frame obsoleto para cámara {cam_id}")
            return
        
        if cam_id not in object_tracker: object_tracker[cam_id] = {}
        tracker = object_tracker[cam_id]

        for category, objs in data[DATA_OBJETOS_DICT].items():
            for new_object in objs:
                new_coords  = new_object[DATA_OBJETO_COORDENADAS]
                new_id      = new_object[DATA_OBJETO_ID_TRACKING]
                new_obj_id  = new_object[DATA_OBJETO_ID_CONCATENADO]
                match_found = False

                # Primero, si el ID ya se encuentra en el tracker, lo actualizamos.
                if new_id in tracker:
                    entry = tracker[new_id]
                    entry[TRACKER_OBJECT_ID]      = new_obj_id
                    entry[TRACKER_LAST_COORDS]    = new_coords
                    entry[TRACKER_LAST_TIME]      = epoch
                    entry[TRACKER_MISSED]         = 0  
                    match_found                   = True

                    # Verificamos si ya pasó el umbral de tiempo desde el start_time y no se envió notificación
                    max_time = int(r.hget(NAME_CONTAINER,f'{cam_id}:{category}') or UMBRAL_TIEMPO)
                    if (epoch - entry[TRACKER_START_TIME] >= max_time) and (not entry.get(TRACKER_ALERT_SENT, False)):
                        logger.info(f"El objeto {new_id} en cámara {cam_id} ha superado el límite de tiempo permitido (start_time: {entry['start_time']}, actual: {epoch})")
                        sendEvent(new_object[DATA_OBJETO_EPOCH_OBJECT], epoch, cam_id, new_obj_id, new_id, category,'El objeto sobrepaso el limite de tiempo', 2)
                        entry[TRACKER_ALERT_SENT] = True
                else:
                    # Si no se encontró por ID, se intenta buscar coincidencias basadas en coordenadas.
                    for tracked_id, info in tracker.items():
                        if info.get(TRACKER_CATEGORY) == category:
                            # La función is_inside se utiliza para determinar si new_coords es similar al área registrada.
                            if is_inside(new_coords, expand_bbox(info[TRACKER_LAST_COORDS])):
                                logger.info(f"Coincidencia por coordenadas: objeto {new_id} se asocia con tracker id {tracked_id} en cámara {cam_id}")
                                info[TRACKER_LAST_COORDS] = new_coords
                                info[TRACKER_LAST_TIME] = epoch
                                info[TRACKER_MISSED] = 0
                                info[TRACKER_OBJECT_ID] = new_obj_id
                                match_found = True
                                # Actualizamos el ID del nuevo objeto para ser consistente con el tracker.
                                new_object[DATA_OBJETO_ID_TRACKING] = tracked_id
                                max_time = int(r.hget(NAME_CONTAINER,f'{cam_id}') or UMBRAL_TIEMPO)
                                # Verificar si se debe enviar la notificación (usando el start_time ya existente)
                                if (epoch - info[TRACKER_START_TIME] >= max_time) and (not info.get(TRACKER_ALERT_SENT, False)) and (category != CATEGORY_PARKING):
                                    sendEvent(new_object[DATA_OBJETO_EPOCH_OBJECT], epoch, cam_id, new_obj_id, new_id, category,'El objeto sobrepaso el limite de tiempo', 2)
                                    logger.info(f"El objeto (tracker id: {tracked_id}) en cámara {cam_id} ha superado el límite de tiempo permitido")
                                    info[TRACKER_ALERT_SENT] = True
                                break

                # Si no se encontró match ni por ID ni por coordenadas, se considera un nuevo objeto.
                if not match_found:
                    logger.info(f"Objeto nuevo detectado: {new_id} en cámara {cam_id}")
                    tracker[new_id] = {
                        TRACKER_LAST_COORDS: new_coords,
                        TRACKER_START_TIME:  epoch,   
                        TRACKER_LAST_TIME:   epoch,
                        TRACKER_MISSED:      0,
                        TRACKER_CATEGORY:    category,
                        TRACKER_ALERT_SENT:  False,  
                        TRACKER_OBJECT_ID:   new_obj_id 
                    }
                    new_object[DATA_OBJETO_TIME] = epoch
                    sendEvent(new_object[DATA_OBJETO_EPOCH_OBJECT], epoch, cam_id, new_obj_id, new_id, category, message = 'Objeto Nuevo')


        # Incrementar contador de frames perdidos para aquellos objetos del tracker que no se detectaron en el frame actual.
        detected_ids = { obj[DATA_OBJETO_ID_TRACKING] 
                         for objs in data[DATA_OBJETOS_DICT].values() 
                         for obj in objs }
        for obj_id in list(tracker.keys()):
            if obj_id not in detected_ids:
                tracker[obj_id][TRACKER_MISSED] += 1
                if tracker[obj_id][TRACKER_MISSED] > UMBRAL_MISSED:
                    logger.info(f"Objeto {obj_id} en cámara {cam_id} perdido tras {tracker[obj_id]['missed']} frames sin detección.")
                    sendEvent(tracker[obj_id][TRACKER_LAST_TIME], tracker[obj_id][TRACKER_LAST_TIME], cam_id, tracker[obj_id][TRACKER_OBJECT_ID], obj_id, category, message = 'Objeto Saliendo')
                    del tracker[obj_id]
        
        # El número actual de vehículos (o vehículos en seguimiento) es la cantidad de elementos en el tracker.
        num_vehiculos = len(tracker)
        # logger.info(f"La cantidad de vehículos en cámara {cam_id} es {num_vehiculos}")

        # Actualizamos los datos globales de la cámara y el tracker.
        coords_cameras[cam_id] = data
        object_tracker[cam_id] = tracker

        return True

    except Exception as e:
        logger.error(f"Error procesando coordenadas para la cámara {cam_id}: {str(e)}")
        return False

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
        logger.info(f"Publicando resultado de detección vía publicador asíncrono: {result}")
        if publisher is not None:
            publisher.publish_async(result)
        else:
            logger.error(LOG_SEND_MSG)

def main():
    global publisher, r
    publisher = ExamplePublisher(AMQP_URL)
    publisher.start()
    # r = redis.Redis(connection_pool=redis_pool, decode_responses=False)

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