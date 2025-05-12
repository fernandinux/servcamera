import time
import numpy as np
import cv2
import redis
import ast
import re
from config import *
from config_logger import configurar_logger

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

# Parámetro para controlar la posición horizontal de los puntos (0.2 = 20% desde los bordes)
POINT_HORIZONTAL_OFFSET = 0.2

def parse_zones_and_polygons(zone_restricted_str):
    """Parsea los polígonos de zonas restringidas desde un string JSON"""
    if not zone_restricted_str or str(zone_restricted_str).strip().lower() in ('none', '{}', '[]'):
        return [], []

    try:
        # Normalización robusta del string
        normalized_str = str(zone_restricted_str).strip()
        normalized_str = re.sub(r"'(\d+)'", r'"\1"', normalized_str)
        
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
    """Crea una máscara binaria con las zonas restringidas"""
    mask = np.zeros(resolution, dtype=np.uint8)

    for poligono in restringidas:
        try:
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [puntos], color=255)
        except Exception as e:
            logger.error(f"Error dibujando polígono {poligono}: {str(e)}")    
    return mask

def adjust_coords_for_lower_part(vehicle_coords, lower_percentage=MASK_LOWER_PERCENTAGE):
    """Ajusta el bounding box para considerar solo la parte inferior del vehículo"""
    x1, y1, x2, y2 = vehicle_coords
    height = y2 - y1
    y1_adjusted = y2 - int(height * lower_percentage)
    y1_adjusted = max(y1_adjusted, 0)
    y2 = min(y2, CAMERA_RESOLUTION[1])
    return (x1, y1_adjusted, x2, y2)

def get_detection_points(adjusted_bbox):
    """Genera dos puntos cerca de los extremos superiores del bbox ajustado"""
    try:
        x1, y1, x2, y2 = adjusted_bbox
        width = x2 - x1
        
        # Punto izquierdo (20% desde el borde izquierdo)
        left_x = x1 + int(width * POINT_HORIZONTAL_OFFSET)
        left_point = (left_x, y1)
        
        # Punto derecho (20% desde el borde derecho)
        right_x = x2 - int(width * POINT_HORIZONTAL_OFFSET)
        right_point = (right_x, y1)
        
        # Asegurar que los puntos estén dentro de los límites
        left_point = (max(0, min(left_x, CAMERA_RESOLUTION[0]-1)), max(0, min(y1, CAMERA_RESOLUTION[1]-1)))
        right_point = (max(0, min(right_x, CAMERA_RESOLUTION[0]-1)), max(0, min(y1, CAMERA_RESOLUTION[1]-1)))
        
        return [left_point, right_point]
    except Exception as e:
        logger.error(f"Error calculando puntos de detección: {str(e)}")
        return [(x1, y1), (x2, y1)]  # Fallback a esquinas superiores

def en_area_restringida(points, mask):
    """Determina si ALGÚN punto está dentro del área restringida"""
    for (x, y) in points:
        if 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]:
            if mask[y, x] > 0:
                return True
    return False

def procesamiento_coordenadas_sync(data, publish_callback):
    """Función principal de procesamiento"""
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()

    try:
        # 1. Parsear zonas y polígonos
        zone_ids, polygons = parse_zones_and_polygons(data.get(DATA_COORDS, ""))
        
        if not polygons:
            logger.debug(f"Cámara {cam_id} - Sin polígonos definidos, descartando")
            return
        
        # 2. Crear máscaras individuales por zona
        zone_masks = {
            zone_id: crear_mascara_area([polygon], CAMERA_RESOLUTION[::-1])
            for zone_id, polygon in zip(zone_ids, polygons)
        }

        # 3. Estructura de salida
        output = {
            "camera_id": cam_id,
            "epoch_frame": data.get(DATA_EPOCH_FRAME, 0),
            "n_objects": data.get("n_objects", 0),
            "zone_restricted": data.get(DATA_COORDS, ""),
            "object_dict": {}
        }

        # 4. Procesar cada objeto
        for category, objects in data.get(DATA_OBJETOS_DICT, {}).items():
            output["object_dict"][category] = []
            
            for obj in objects:
                # 4.1. Obtener coordenadas y ajustar
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                adjusted_coords = adjust_coords_for_lower_part(coords)
                
                # 4.2. Obtener los dos puntos de detección
                detection_points = get_detection_points(adjusted_coords)
                
                # 4.3. Verificar si alguno de los puntos está en zona restringida
                detected_zones = [
                    zone_id
                    for zone_id, mask in zone_masks.items()
                    if en_area_restringida(detection_points, mask)
                ]

                alert = None
                tracking_id = obj.get(DATA_TRAKING_ID)

                if tracking_id and detected_zones:
                    if tracking_id not in vehicle_timers.get(cam_id, {}):
                        vehicle_timers.setdefault(cam_id, {})[tracking_id] = current_time
                        
                        # Determinar qué punto activó la detección
                        entry_side = "left" if en_area_restringida([detection_points[0]], zone_masks[detected_zones[0]]) else "right"
                        
                        alert = {
                            "type": "ingreso",
                            "message": f"Ingreso detectado en zona(s): {', '.join(detected_zones)}",
                            "entry_side": entry_side,
                            "detection_points": detection_points
                        }

                        logger.info(f"TIEMPO PROCESAMIENTO OBJETO EN ZONA: {time.time() - start_time}s")
                        
                    else:
                        elapsed = current_time - vehicle_timers[cam_id][tracking_id]
                        if elapsed > PERMANENCE_THRESHOLD:
                            alert = {
                                "type": "permanencia",
                                "message": f"Superó Umbral de permanencia de {elapsed:.1f}s en zona(s): {', '.join(detected_zones)}"
                            }
                            vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer

                logger.info(f"TIEMPO PROCESAMIENTO OBJETO: {time.time() - start_time}s")

                # 4.4. Construir objeto final
                output["object_dict"][category].append({
                    **obj,
                    "zones_interest": detected_zones,
                    "Alerta": alert,
                    "detection_points": detection_points
                })

        publish_callback(output)

        epoch_frame = data.get(DATA_EPOCH_FRAME, 0)
        logger.info(f"EPOCH_FRAME: {epoch_frame}")

        logger.info(f"Tiempo PUBLICACION: {time.time() - start_time}s")

        logger.info(f"Cámara {cam_id} - Publicado con {sum(len(v) for v in output['object_dict'].values())} objetos")

    except Exception as e:
        logger.error(f"Error en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Tiempo total: {time.time() - start_time:.2f}s")