import time
from config import *
from config_logger import configurar_logger
import numpy as np
import cv2
import redis
import ast


logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Diccionario para almacenar el tiempo de entrada
vehicle_timers = {}

# Pool de conexiones Redis
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT
)

def crear_mascara_area(restringidas, resolution):
    for restringida in restringidas:

        mask = np.zeros(resolution, dtype=np.uint8)

        # # Cerrar el polígono si no está cerrado ******
        # if not np.array_equal(restringida[0], restringida[-1]):
        #     puntos_cerrados = np.vstack([restringida, restringida[0]])
        # else:
        #     puntos_cerrados = restringida


        #VERIFICAAAAAR SI ES PUNTOS CERRADOS O RESTRINGIDA EN LOS PARAMS
        puntos = np.array(restringida, dtype=np.int32)
        cv2.fillPoly(mask, [puntos], color=255)
    return mask

def en_area_restringida(bbox, mask):
    x1, y1, x2, y2 = bbox
    roi = mask[y1:y2, x1:x2]
    return cv2.countNonZero(roi) > 0

def adjust_coords_for_lower_part(vehicle_coords, lower_percentage=MASK_LOWER_PERCENTAGE):
    x1, y1, x2, y2 = vehicle_coords
    height = y2 - y1
    y1_adjusted = y2 - int(height * lower_percentage)
    y1_adjusted = max(y1_adjusted, 0)
    y2 = min(y2, CAMERA_RESOLUTION[1])
    return (x1, y1_adjusted, x2, y2)

def get_points_from_camera_id(data,cam_id):
    try:
        # Obtener la cadena de zone_restricted
        zone_restricted_str = data[DATA_COORDS]
        coords = ast.literal_eval(zone_restricted_str)

        coords = coords["1"] #PROPOSITO RECIBIDO EXCHANGE
        
        # Log: Coordenadas convertidas
        #logger.info(f"Coordenadas convertidas para la cámara {cam_id}: {coords}")

        return coords
    
    except (ValueError, SyntaxError) as e:
        logger.error(f"Error al convertir zone_restricted: {str(e)}")
        return []  

def check_if_in_restricted_area(cam_id, coords, mask):
    return en_area_restringida(coords, mask)

def procesamiento_coordenadas(data, publish_callback):

    # Iniciar el cronómetro
    start_time = time.time()
    
    cam_id = data[DATA_CAMERA]

    current_time = time.time()
    logger.info(f"Procesando datos de la cámara {cam_id}")

    try:
        RESTRICTED_AREAS_BY_CAMERA_ID = get_points_from_camera_id(data, cam_id)
        #puntos_poligono = get_points_from_camera_id(cam_id)
        mask = crear_mascara_area(RESTRICTED_AREAS_BY_CAMERA_ID, CAMERA_RESOLUTION[::-1])
        
        # Verificar existencia de object_dict
        if DATA_OBJETOS_DICT not in data:
            logger.error(f"Campo '{DATA_OBJETOS_DICT}' no encontrado en datos")
            return
        
          # Verificar existencia de vehicle_timers para esta cámara
        if cam_id not in vehicle_timers:
            vehicle_timers[cam_id] = {}

        
            
        for categoria, new_boxes in data[DATA_OBJETOS_DICT].items():
            for new_box in new_boxes:
                tracking_id = new_box.get(DATA_TRAKING_ID, None)
                if not tracking_id:
                    continue
                
                new_coords = new_box.get(DATA_OBJETO_COORDENADAS, (0,0,0,0))
                adjusted_coords = adjust_coords_for_lower_part(new_coords)
                
                if check_if_in_restricted_area(cam_id, adjusted_coords, mask):
                    # Manejo de alertas de ingreso
                    if cam_id not in vehicle_timers:
                        vehicle_timers[cam_id] = {}

                    if tracking_id not in vehicle_timers[cam_id]:
                        vehicle_timers[cam_id][tracking_id] = current_time
                        alert = {
                            'camera_id': cam_id,
                            'category': 1,
                            'message': 'Vehículo detectado en área restringida',
                            'type': 1,
                            'sub_type' : 1,
                            'epoch_object': new_box.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                            'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                            'object_id': new_box.get(DATA_OBJETO_ID_CONCATENADO, 0),
                            'n_objects': data.get(DATA_N_OBJECTOS, 0),
                            'object_dict': data.get(DATA_OBJETOS_DICT, 0),
                            'id_tracking': new_box.get(DATA_TRAKING_ID, 0),
                            'zone_restricted': data.get(DATA_COORDS, 0)
                        }
                        publish_callback(alert)
                    
                    # Manejo de alertas de permanencia
                    else:
                        elapsed_time = current_time - vehicle_timers[cam_id][tracking_id]
                        if elapsed_time > PERMANENCE_THRESHOLD:
                            alert = {
                                'camera_id': cam_id,
                                'category': 1,
                                'message': f'Permanencia de Vehículo: {elapsed_time:.2f}s',
                                'type': 1,  
                                'sub_type' : 2,  # subTipo 2 para permanencia
                                'epoch_object': new_box.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                                'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                                'object_id': new_box.get(DATA_OBJETO_ID_CONCATENADO, 0),
                                'n_objects': data.get(DATA_N_OBJECTOS, 0),
                                'object_dict': data.get(DATA_OBJETOS_DICT, 0),
                                'id_tracking': new_box.get(DATA_TRAKING_ID, 0),
                                'zone_restricted': data.get(DATA_COORDS, 0)
                            }
                            publish_callback(alert)
                            vehicle_timers[tracking_id] = current_time  # Reset timer
                            
                else:
                    if cam_id in vehicle_timers and tracking_id in vehicle_timers[cam_id]:
                        del vehicle_timers[cam_id][tracking_id]
                        #logger.info(f"Tracking ID eliminado: {tracking_id} de cámara {cam_id}")

                    # if tracking_id in vehicle_timers:
                    #     del vehicle_timers[tracking_id]

    except KeyError as e:
        logger.error(f"Error de clave faltante: {str(e)}")
    except Exception as e:
        logger.error(f"Error general: {str(e)}")

        # Detener el cronómetro
    end_time = time.time()

    # Calcular el tiempo transcurrido
    elapsed_time = end_time - start_time
    logger.info(f"Tiempo total del proceso: {elapsed_time} segundos")