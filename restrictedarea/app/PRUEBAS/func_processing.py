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

def procesamiento_coordenadas_sync(data, publish_callback):
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()

    try:
        # 1. Parsear zonas y polígonos
        zone_ids, polygons = parse_zones_and_polygons(data.get(DATA_COORDS, ""))
        
        # Si no hay polígonos definidos, descartar el mensaje
        if not polygons:
            logger.debug(f"Cámara {cam_id} - Sin polígonos definidos, descartando")
            return
        
        # 2. Crear máscaras individuales por zona
        zone_masks = {
            zone_id: crear_mascara_area([polygon], CAMERA_RESOLUTION[::-1])
            for zone_id, polygon in zip(zone_ids, polygons)
        }

        # 3. Estructura de salida combinada
        output = {
            "camera_id": cam_id,
            "epoch_frame": data.get(DATA_EPOCH_FRAME, 0),
            "n_objects": data.get("n_objects", 0),
            "zone_restricted": data.get(DATA_COORDS, ""),  # Original
            "object_dict": {}
        }

        has_relevant_objects = False  # Bandera para detectar si hay objetos relevantes

        # 4. Procesar cada objeto
        for category, objects in data.get(DATA_OBJETOS_DICT, {}).items():
            output["object_dict"][category] = []
            
            for obj in objects:
                # 4.1. Detección de zonas
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                adjusted_coords = adjust_coords_for_lower_part(coords)
                detected_zones = [
                    zone_id
                    for zone_id, mask in zone_masks.items()
                    if en_area_restringida(adjusted_coords, mask)
                ]
                
                # Solo procesar si está en alguna zona
                if detected_zones:
                    has_relevant_objects = True
                    alert = None
                    tracking_id = obj.get(DATA_TRAKING_ID)

                    if tracking_id and detected_zones:
                        if tracking_id not in vehicle_timers.get(cam_id, {}):
                            vehicle_timers.setdefault(cam_id, {})[tracking_id] = current_time
                            alert = {
                                "type": "ingreso",
                                "message": f"Ingreso detectado en zona(s): {', '.join(detected_zones)}"
                            }
                        else:
                            elapsed = current_time - vehicle_timers[cam_id][tracking_id]
                            if elapsed > PERMANENCE_THRESHOLD:
                                alert = {
                                    "type": "permanencia",
                                    "message": f"Superó Unbral de permanencia de {elapsed:.1f}s en zona(s): {', '.join(detected_zones)}"
                                }
                                vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer

                    # 4.3. Construir objeto final
                    output["object_dict"][category].append({
                        **obj,  # Todos los campos originales
                        "zones_interest": detected_zones,
                        "Alerta": alert  # None si no hay alerta
                    })


        # Solo publicar si hay objetos relevantes
        if has_relevant_objects:
            publish_callback(output)
            logger.info(f"Cámara {cam_id} - Publicado con {sum(len(v) for v in output['object_dict'].values())} objetos relevantes")   

        else:

            logger.debug(f"Cámara {cam_id} - Sin objetos en zonas de interés, descartando")

    except Exception as e:
        logger.error(f"Error en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Tiempo total: {time.time() - start_time:.2f}s")


        