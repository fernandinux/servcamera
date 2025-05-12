import logging
import json
import time
import threading
import cv2 # type: ignore
import numpy as np # type: ignore
import statistics
import datetime
import redis # type: ignore

from config_logger import configurar_logger
from config import *
from publisher import ExamplePublisher

coords_cameras = {}
logger = configurar_logger( name    = FILE_NAME_LOG,
                            log_dir = FILE_PATH_LOG,
                            nivel   = logging.DEBUG)
r       = redis.Redis(host  = REDIS_HOST, 
                      port  = REDIS_PORT, 
                      db    = REDIS_DB)

def sendEnvent(cam, epoch_frame, message, mode = 2):
    alert = {
            'category'    : 5,
            'type'        : mode,
            'message'     : message,
            'epoch_frame' : epoch_frame,
            'camera_id'   : cam,
            }
    
    logger.info(alert)
    thread = threading.Thread(target=publish_detection_result, args=(alert,))
    thread.start()  
    
def sendDetalle(day, lapse_time, data, cam, mode, epoch_frame):
    category = int(f"{day}{lapse_time}{int(cam)}{mode}")
    alert = {
            'category'          : category,
            'valor'             : data,
            'id_evento_tipo'    : mode,
            'id_evento_subtipo' : lapse_time,
            'id_camara'         : int(cam),
            'epoch'             : int(epoch_frame),
            'fecha_registro'    : str(day),
            }
    logger.info(alert)
    thread = threading.Thread(target=publish_detection_result, args=(alert.copy(),))
    thread.start()

def compareResults(values):
    mean, deviation = getStatistics(values)
    logger.info(f'mean: {mean}, deviation: {deviation}, values: {values}')

    if values[0] < mean - deviation:
        logger.info("Congestión detectada")
        return True
    elif values[0] > mean + deviation:
        logger.info("Flujo más rápido de lo normal")
        return False
    else:
        logger.info("Flujo normal")
        return False

def getStatistics(values):
    return np.nanmean(values), np.nanstd(values)

def getValues(style, cam_id, day, lapse_index):
    return [
        float(r.hget(style, f'{cam_id}:{day - LAPSE_DAY*i}:{lapse_index}').decode('utf-8'))
        if r.hget(style, f'{cam_id}:{day - LAPSE_DAY*i}:{lapse_index}') is not None else np.nan
        for i in range(MAX_WEEK+1)
    ]

# def getValues(style, cam_id, day, lapse_index):
#     values = []
#     for i in range(MAX_WEEK + 1):
#         key = f'{cam_id}:{day - LAPSE_DAY * i}:{lapse_index}'
#         value = r.hget(style, key)
        
#         if value is not None:
#             try:
#                 # Intentar convertir el valor a float
#                 values.append(float(value))
#             except ValueError:
#                 # Si falla la conversión, corregir el valor y actualizarlo en Redis
#                 try:
#                     corrected_value = float(eval(value))  # Convierte 'np.float64(0.4996)' a 0.4996
#                     values.append(corrected_value)
#                     r.hset(style, key, corrected_value)
#                     logger.warning(f"Valor corregido en Redis: {key} -> {corrected_value}")
#                 except Exception as e:
#                     logger.error(f"Error al corregir el valor {value} para {key}: {str(e)}")
#                     values.append(np.nan)
#         else:
#             values.append(np.nan)
    
#     return values

def procesamiento_coordenadas(day, lapse_index, cam_id, epoch_frame):
    flag_event = False
    try:
        for mode, style in enumerate(['counted_vehicles', 'speed_vehicles']):
            values = getValues(style, cam_id, day, lapse_index)
            logger.info(values)
            current_value = values[0] 

            if not np.isnan(current_value):
                sendDetalle(day, lapse_index, current_value, cam_id, mode, epoch_frame)
                if compareResults(values): flag_event +=1
                    # logger.info(f"Values to {cam_id} in {style} in lapse {lapse_index} are {values} if speed is {current_value}")    
        if flag_event == 2: 
            sendEnvent(cam_id, int(epoch_frame*1000, mode = 1), message = '1 minutos de congestión')
            return True
        return False
           
    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")
        return None

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

def wait_until_next_interval():
    """Espera hasta el próximo minuto + SECONDS_DELAY segundos (por ejemplo: 12:01:05, 12:02:05, etc.)"""
    now = datetime.datetime.now()
    next_time = now.replace(second=SECONDS_DELAY, microsecond=0)
    if now.second >= SECONDS_DELAY:
        next_time += datetime.timedelta(minutes=1)
    wait_seconds = (next_time - now).total_seconds()
    logger.info(f"Esperando {wait_seconds:.2f} segundos hasta la próxima ejecución...")
    time.sleep(wait_seconds)

def obtener_indice_lapso(epoch):
    seconds = (epoch) % SECONDS_DAY
    return int(epoch // SECONDS_DAY), int(seconds // LAPSE_TIME)

def read_and_process_redis_data():
    mydate = time.time()
    day, lapse_index = obtener_indice_lapso(int(mydate) - 2*SECONDS_DELAY)
    keys = r.smembers(f"counted_vehicles:{day}:{lapse_index}")
    logger.info(f'keys: {keys}')

    for key in keys:
        try:
            cam = key.decode('utf-8')
            if cam is None:
                continue
            congestion = procesamiento_coordenadas(day, lapse_index, cam, mydate)
            congestion_key  = f"traffic_congestion:{cam}"
            congestion_limit= f"traffic_congestion:limit:{cam}"
            congestion_date = f"traffic_congestion:date:{cam}"
            alert_sent_key  = f"traffic_congestion:alert:{cam}"
            last_congestion_date = float(r.get(congestion_date) or mydate)

            if congestion and (mydate - last_congestion_date) < LIMIT_INTERVAL_TIME:
                current_count = int(r.get(congestion_key) or 0) + 1
                r.set(congestion_key, current_count)
                if current_count >= int(r.get(congestion_limit) or LIMIT_CONGESTION) and not r.exists(alert_sent_key):
                    logger.info(f"10 eventos consecutivos de congestión detectados en la cámara {cam}")
                    sendEnvent(cam, int(mydate*1000), message = '10 minutos de congestión')
                    r.set(alert_sent_key, int(mydate*1000))  # Marcar como enviado
            else:
                if r.exists(alert_sent_key):
                    logger.info(f"Congestión terminada en la cámara {cam}")
                    sendEnvent(cam, int(r.get(alert_sent_key)), message = 'Termino la congestión', mode = 1)
                    r.delete(alert_sent_key)  
                r.set(congestion_key, 0)

            r.set(congestion_date, mydate)
            # r.hdel('counted_vehicles', f'{cam}:{day-END_DAY}:{lapse_index}')
            # r.hdel('speed_vehicles', f'{cam}:{day-END_DAY}:{lapse_index}')

        except Exception as e:
            logger.error(f"Error al procesar clave {key}: {str(e)}")

    # r.delete(f"counted_vehicles:{day-END_DAY}:{lapse_index}")

def main():
    global publisher,r
    publisher = ExamplePublisher(AMQP_URL)
    publisher.start()

    logger.info("Iniciando procesamiento desde Redis cada minuto + 5 segundos...")

    try:
        while True:
            wait_until_next_interval()
            logger.info("Leyendo datos desde Redis y procesando...")
            read_and_process_redis_data()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    finally:
        publisher.stop()

if __name__ == "__main__":
    main()
