import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore

from datetime import datetime
from config_logger import configurar_logger
from config import *
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher
import redis # type: ignore

logger = configurar_logger( name    = FILE_NAME_LOG, 
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)

redis_pool = redis.ConnectionPool(
    host='10.23.63.79', 
    port=6379, 
    db=0,
    socket_timeout=5
)

def extract_region(frame, region):
    mid_height, mid_width = (frame.shape[0] // LEN_REGIONS, frame.shape[1] // LEN_REGIONS)
    return frame[mid_height*region[1]:mid_height*region[3], mid_width*region[0] :mid_width*region[2]]

def classify_colors_multiple_regions(regions_hsv):
    total_pixels = sum(region.shape[0] * region.shape[1] for region in regions_hsv)  
    color_counts = {color: 0 for color in color_ranges.keys()}  
    
    for region_hsv in regions_hsv:
        for color_name, (lower, upper) in color_ranges.items():
            lower = np.array(lower, dtype=np.uint8)
            upper = np.array(upper, dtype=np.uint8)

            mask = cv2.inRange(region_hsv, lower, upper)
            color_counts[color_name] += np.count_nonzero(mask)

    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    if len(sorted_colors) > 1:
        top_color, top_count = sorted_colors[0]
        second_color, second_count = sorted_colors[1]
        return (top_color, (top_count / total_pixels) * 100), (second_color, (second_count / total_pixels) * 100)
    elif len(sorted_colors) == 1:
        top_color, top_count = sorted_colors[0]
        return (top_color, (top_count / total_pixels) * 100), (None, 0) 
    else:
        return (None, 0), (None, 0)

def process_image_cropped(region):
    dominant_color, second_dominant_color = classify_colors_multiple_regions(region)
    if dominant_color[0] in VERIFY_COLOR: 
        dominant_color_name, precision = second_dominant_color if abs(dominant_color[1] - second_dominant_color[1]) < UMBRAL_DIF else dominant_color
    else:
        dominant_color_name, precision = dominant_color
    return dominant_color_name, int(precision)

def getDate(epoch):
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime(FILE_DATE), dt.strftime(FILE_HOUR)

def getPath(camera, epoch_frame, epoch_object):
    day, hour = getDate(epoch_frame / EPOCH_FORMAT)
    output_path = f"/{FILE_OUTPUT}/{camera}/{day}/{hour}/{FILE_OBJECT}/{epoch_object}.{FILE_FORMAT}"
    return output_path

def getImg(camera, objeto_id):
    try:
        r = redis.Redis(connection_pool=redis_pool, decode_responses=False)
        inicio_tiempo = time.time()
        objeto_id = int(f"1{objeto_id}")
        
        image_bytes = r.get(objeto_id)
        if not image_bytes:
            logger.error(f"Objeto {objeto_id} no existe en Redis")
            return None, False
        
        logger.info(f"Tiempo obtención Redis: {time.time() - inicio_tiempo:.3f}s")
        
        try:
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            logger.info(f"Tiempo buffer to array: {time.time() - inicio_tiempo:.3f}s")
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            logger.info(f"Tiempo array to img: {time.time() - inicio_tiempo:.3f}s")
            
            if img is None:
                logger.error("Formato de imagen inválido")
                return None
            return img
        except Exception as e:
            logger.exception("Error decodificando imagen")
            return 
    except Exception as e: 
        logger.error(f'{LOG_READ_IMG}: {e}')
        return None

def detectAttribute(img):
    region_hsv = [cv2.cvtColor(extract_region(img, region), cv2.COLOR_BGR2HSV) for region in REGIONS]
    return process_image_cropped(region_hsv)

def processFrame(message):
    for _, objects in message[DATA_OBJESTOS_LIST].items():
        for obj in objects:
            obj[DATA_ATRIBUTO_STATUS] = 0
            if obj[DATA_OBJETO_CANDIDATO]: 
                obj[DATA_ATRIBUTO_ID] = ATTRIBUTE_ID
                obj[DATA_ATRIBUTO_INIT_TIME] = int(time.time()*EPOCH_FORMAT)
                try:
                    init_time_test = time.time()
                    img = getImg(message[DATA_CAMERA], obj[DATA_OBJETO_ID_CONCATENADO])
                    final_time_test = time.time()
                    if final_time_test-init_time_test > UMBRAL_TIME_RCBD_IMG: logger.warning(f'{LOG_TIME_READ} es {final_time_test-init_time_test} mayor a {UMBRAL_TIME_RCBD_IMG}')

                    init_time_test = time.time()
                    obj[DATA_ATRIBUTO_DESCRIPITON], obj[DATA_ATRIBUTO_ACCURACY] = detectAttribute(img)
                    final_time_test = time.time()
                    if final_time_test-init_time_test > UMBRAL_TIME_SEND_MSG: logger.warning(f'{LOG_TIME_SEND} es {final_time_test-init_time_test} mayor a {UMBRAL_TIME_SEND_MSG}')

                    obj[DATA_ATRIBUTO_FINAL_TIME] = int(time.time()*EPOCH_FORMAT)
                    obj[DATA_ATRIBUTO_STATUS] = 1

                except Exception as e: 
                    logger.error(f"{LOG_FUNC_COLOR}: {e}")
                    return False
    publisher.publish_async(message)
    return True

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    thread = threading.Thread(target=procesar_mensaje, args=(body,))
    thread.start()

def procesar_mensaje(body):
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Datos recibidos: {data}")
        succes = processFrame(data)
        logger.info(f"Mensaje recibido para cámara {data[DATA_CAMERA]}: {data} Procesando")
    
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