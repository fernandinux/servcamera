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

logger = configurar_logger( name    = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)

redis_pool = redis.ConnectionPool(
    host='10.23.63.56', 
    port=6379, 
    db=0,
    socket_timeout=5
)

def drawVechicles(new_data, name, zone):
    imagen = np.ones((1080, 1920, 3), dtype=np.uint8) * 255
    pts = np.array(zone, np.int32)
    pts = pts.reshape((-1, 1, 2))
    for draw_data in new_data:
        bbox = draw_data[DATA_OBJETO_COORDENADAS]
        cv2.rectangle(imagen, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
    cv2.polylines(imagen, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
    cv2.imwrite(f'/output/{name}.jpg', imagen)

def area(a, b, c):
    """Calcula el área de un triángulo dado por 3 puntos."""
    return abs((a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1])) / 2.0)

def point_in_triangle(p, t1, t2, t3):
    """Devuelve True si p está dentro del triángulo definido por (t1, t2, t3)."""
    A = area(t1, t2, t3)
    A1 = area(p, t2, t3)
    A2 = area(t1, p, t3)
    A3 = area(t1, t2, p)
    return abs(A - (A1 + A2 + A3)) < 1e-5  # Si las áreas coinciden, está dentro

def point_in_quadrilateral(p, quad):
    """Divide el cuadrilátero en dos triángulos y verifica si el punto está en alguno de ellos."""
    return (point_in_triangle(p, quad[0], quad[1], quad[2]) or
            point_in_triangle(p, quad[0], quad[2], quad[3]))

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

def sendEnvent(epoch_object, epoch_frame, camera_id, object_id, mode):
    alert = {
            'category': 1,
            'type': 2,
            'epoch_object': epoch_object,
            'epoch_frame': epoch_frame,
            'camera_id': camera_id,
            'object_id': object_id,
            'message': 'Espacio Ocupado' if mode == 1 else 'Espacio Disponible' 
            }
    thread = threading.Thread(target=publish_detection_result, args=(alert,))
    thread.start()    

def procesamiento_coordenadas(data):
    cam_id = data[DATA_CAMERA]
    try:
        data_old = coords_cameras.get(cam_id, {})
        if data[DATA_EPOCH_FRAME] <=  data_old.get(DATA_EPOCH_FRAME, 0):
            logger.info(f"Frame obsoleto para cámara {cam_id}")
            return
        
        new_data = []
        if cam_id == '5': ZONE = [(1365,53),(1501,44),(1583,1072),(1020,1078)]  
        elif cam_id == '27': ZONE = [(1536,621),(1638,558),(615,207),(468,249)]
        else: ZONE = [(280,443),(278,1),(432,0),(620,427)]

        # Iterar sobre cada categoría y sus cajas en la nueva data
        logger.info(f"LA CANTIDAD DE OBJETOS PARA LA CAMARA {cam_id} SON {len(data[DATA_OBJETOS_DICT].get('21', []))}")
        for new_object in data[DATA_OBJETOS_DICT].get('21', []):
            if new_object['is_new']:
                new_coords = new_object[DATA_OBJETO_COORDENADAS]
                logger.info(f"Vamos a analizar si {new_object[DATA_OBJETO_ID_TRACKING]} es un nuevo vehiculo")
                flag = True
                for obj_old in data_old.get(DATA_OBJETOS_DICT,[]):
                    old_coords = obj_old[DATA_OBJETO_COORDENADAS]
                    if is_inside(new_coords, expand_bbox(old_coords)):
                        new_object[DATA_OBJETO_TIME] = obj_old[DATA_OBJETO_TIME]
                        new_data.append(new_object)
                        flag = False
                        logger.info(f'EL OBJETO {new_object[DATA_OBJETO_ID_TRACKING]} ES UN OBJETO ANTERIOR {obj_old[DATA_OBJETO_ID_TRACKING]} CON UN TIEMPO {data[DATA_EPOCH_FRAME] - new_object[DATA_OBJETO_TIME]}')
                        break
                if flag:
                    x1, y1, x2, y2 = new_coords
                    center_coord = ((x1+x2)/2, (y1+y2)/2)
                    if point_in_quadrilateral(center_coord, ZONE):
                        logger.info(f'OBJETO NUEVO ESTACIONADO')
                        new_data.append(new_object)
                        sendEnvent(new_object[DATA_OBJETO_EPOCH_OBJECT], data[DATA_EPOCH_FRAME], data[DATA_CAMERA],new_object[DATA_OBJETO_ID_CONCATENADO], 1)
                    else:
                        logger.info('ERA UN OBJETO NO ESTACIONADO')
            else:
                for obj_old in data_old.get(DATA_OBJETOS_DICT,[]):
                    if new_object[DATA_OBJETO_ID_TRACKING] == obj_old[DATA_OBJETO_ID_TRACKING]:
                        new_data.append(new_object)
                        new_object[DATA_OBJETO_TIME] = obj_old[DATA_OBJETO_TIME]                    
                        logger.info(f'EL OBJETO {new_object[DATA_OBJETO_ID_TRACKING]} CONTINUA ESTACIONADO CON UN TIEMPO { data[DATA_EPOCH_FRAME] - new_object[DATA_OBJETO_TIME]}')
                        break
                
        if len(new_data)>0: drawVechicles(new_data, data[DATA_EPOCH_FRAME],ZONE)
       
        logger.info(f'La cantidad de vehiculos estacionados en la camara {cam_id} es: {len(new_data)}')
        # Actualizamos la información de coordenadas para la cámara
        data[DATA_OBJETOS_DICT] = new_data
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
        logger.info(f"Publicando resultado de detección vía publicador asíncrono: {result}")
        if publisher is not None:
            publisher.publish_async(result)
        else:
            logger.error(LOG_SEND_MSG)

def main():
    global publisher, r
    publisher = ExamplePublisher(AMQP_URL)
    publisher.start()
    r = redis.Redis(connection_pool=redis_pool, decode_responses=False)

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