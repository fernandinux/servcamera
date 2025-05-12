import time
from config import *
from config_logger import configurar_logger
import numpy as np
import cv2
import redis
import ast
import re


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

def parse_zones_and_polygons(zone_restricted_str):
    # try:
    #     data = ast.literal_eval(zone_restricted_str.replace("'", '"'))
    #     zones = []
    #     polygons = []
        
    #     if isinstance(data, dict):
    #         zones = list(data.keys())  # Extraemos las claves (ej: '21', '10')
            
    #         for key in zones:
    #             items = data[key]
    #             logger.info(f"Zona {key}")
    #             if all(isinstance(p, (tuple, list)) for p in items):
    #                 polygons.append(items)  # Formato nuevo
    #             elif isinstance(items, list) and items and isinstance(items[0], list):
    #                 polygons.extend(items)  # Formato antiguo
        
    #     return zones, [[(int(x), int(y)) for (x, y) in poly] for poly in polygons if len(poly) >= 3]
    # except Exception as e:
    #     logger.error(f"Error parsing zones: {str(e)}")
    #     return [], []
    
    if not zone_restricted_str or str(zone_restricted_str).strip().lower() in ('none', '{}', '[]'):
        return [], []

    try:
        # Normalización robusta del string
        normalized_str = str(zone_restricted_str).strip()
        normalized_str = re.sub(r"'(\d+)'", r'"\1"', normalized_str)  # Convert '21' -> "21"
        
        # Parseo seguro
        data = ast.literal_eval(normalized_str) if normalized_str else {}
        
        zones = []
        all_polygons = []
        
        if isinstance(data, dict):
            for zone_id, polygons in data.items():
                if isinstance(polygons, list):
                    zones.append(str(zone_id))
                    # Asegurar que cada polígono tenga al menos 3 puntos
                    valid_polygons = [
                        [(int(x), int(y)) for (x,y) in poly] 
                        for poly in polygons 
                        if isinstance(poly, list) and len(poly) >= 3
                    ]
                    all_polygons.extend(valid_polygons)
        
        logger.debug(f"Zonas parseadas: {zones} | Polígonos válidos: {len(all_polygons)}")
        return zones, all_polygons
    
    except Exception as e:
        logger.error(f"Error parsing zone_restricted (input: {zone_restricted_str[:50]}...): {str(e)}")
        return [], []
    
def crear_mascara_area(restringidas, resolution):

    mask = np.zeros(resolution, dtype=np.uint8)

        # # Cerrar el polígono si no está cerrado ******
        # if not np.array_equal(restringida[0], restringida[-1]):
        #     puntos_cerrados = np.vstack([restringida, restringida[0]])
        # else:
        #     puntos_cerrados = restringida


        #VERIFICAAAAAR SI ES PUNTOS CERRADOS O RESTRINGIDA EN LOS PARAMS
    for poligono in restringidas:
        try:
            puntos = np.array(poligono, dtype=np.int32)
            cv2.fillPoly(mask, [puntos], color=255)
        except Exception as e:
            logger.error(f"Error dibujando polígono {poligono}: {str(e)}")    
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

def get_zones_and_points_from_camera(data,cam_id):
    try:
        # Obtener la cadena de zone_restricted
        zone_restricted_str = data[DATA_COORDS]
        return parse_zones_and_polygons(zone_restricted_str)

    except Exception as e:
        logger.error(f"Error obteniendo polígonos: {str(e)}")
        return []  

def check_if_in_restricted_area(cam_id, coords, mask):
    return en_area_restringida(coords, mask)

def procesamiento_coordenadas(data, publish_callback, publish_zones_callback=None):
    # Iniciar cronómetro
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()
    logger.info(f"Procesando frame de cámara {cam_id}")

    try:
        # 1. Parseo de zonas y polígonos (formato unificado)
        zone_keys, polygons = parse_zones_and_polygons(data.get(DATA_COORDS, ""))
        logger.debug(f"Cámara {cam_id} - Zonas detectadas: {zone_keys} | Polígonos: {len(polygons)}")

        # 2. Creación de máscara para detección
        mask = crear_mascara_area(polygons, CAMERA_RESOLUTION[::-1]) if polygons else None
        if mask is not None:
            logger.info(f"Cámara {cam_id} - Máscara creada ({np.sum(mask > 0)} píxeles activos)")
        else:
            logger.warning(f"Cámara {cam_id} - No se creó máscara (sin polígonos válidos)")

        # 3. Preparar estructura de salida para zonas
        zones_output = {
            "camera_id": cam_id,
            "epoch_frame": data.get(DATA_EPOCH_FRAME, 0),
            "n_objects": data.get("n_objects", 0),
            "object_dict": {}
        }

        # 4. Verificar existencia de datos requeridos
        if DATA_OBJETOS_DICT not in data:
            logger.error(f"Campo '{DATA_OBJETOS_DICT}' no encontrado")
            return

        # Inicializar timers por cámara si no existen
        if cam_id not in vehicle_timers:
            vehicle_timers[cam_id] = {}

        # 5. Procesar cada categoría de objetos
        for categoria, objetos in data[DATA_OBJETOS_DICT].items():
            zones_output["object_dict"][categoria] = []
            
            for obj in objetos:
                # 5.1 Construir objeto de salida con zonas
                output_obj = {
                    **{k: v for k, v in obj.items()},  # Copia todos los campos originales
                    "zones_interest": zone_keys if obj.get("status_object", False) else []
                }
                zones_output["object_dict"][categoria].append(output_obj)

                # 5.2 Lógica de detección en áreas restringidas (alertas)
                tracking_id = obj.get(DATA_TRAKING_ID)
                if not tracking_id or mask is None:
                    continue

                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                adjusted_coords = adjust_coords_for_lower_part(coords)
                
                if check_if_in_restricted_area(cam_id, adjusted_coords, mask):
                    # Manejo de alertas de ingreso
                    if tracking_id not in vehicle_timers[cam_id]:
                        vehicle_timers[cam_id][tracking_id] = current_time
                        alert = {
                            'camera_id': cam_id,
                            'category': 1,
                            'type': 1,
                            'sub_type': 1,
                            'epoch_object': obj.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                            'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                            'object_id': obj.get(DATA_OBJETO_ID_CONCATENADO, 0),
                            'message': 'Vehículo detectado en área restringida'
                        }
                        publish_callback(alert)
                    
                    # Manejo de alertas de permanencia
                    else:
                        elapsed_time = current_time - vehicle_timers[cam_id][tracking_id]
                        if elapsed_time > PERMANENCE_THRESHOLD:
                            alert = {
                                'camera_id': cam_id,
                                'category': 1,
                                'type': 1,
                                'sub_type': 2,
                                'epoch_object': obj.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                                'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                                'object_id': obj.get(DATA_OBJETO_ID_CONCATENADO, 0),
                                'message': f'Permanencia de Vehículo: {elapsed_time:.2f}s'
                            }
                            publish_callback(alert)
                            vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer
                else:
                    # Limpiar timer si el vehículo salió del área
                    if tracking_id in vehicle_timers.get(cam_id, {}):
                        del vehicle_timers[cam_id][tracking_id]

        # 6. Publicar resultados
        if publish_zones_callback:
            publish_zones_callback(zones_output)
            logger.debug(f"Cámara {cam_id} - Enviado zones_output con {len(zone_keys)} zonas")

    except KeyError as e:
        logger.error(f"Error de clave faltante en cámara {cam_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error crítico en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Cámara {cam_id} - Procesado en {time.time()-start_time:.3f} segundos")
    