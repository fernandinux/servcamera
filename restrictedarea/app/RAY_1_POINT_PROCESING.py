import time
import numpy as np
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

# Parámetros ajustables para la posición del punto de detección
POINT_HORIZONTAL_OFFSET = 0.5  # 20% desde los bordes horizontales (ahora controla el centro)
POINT_VERTICAL_POSITION = 0.7   # 70% desde la parte superior del bbox (30% inferior)

def point_in_polygon(point, polygon):
    """Implementación del algoritmo ray-casting para determinar si un punto está dentro de un polígono"""
    x, y = point
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def parse_zones_and_polygons(zone_data):
    if not zone_data or not isinstance(zone_data, dict):
        return [], []

    try:
        zones = []
        all_polygons = []
        target_zones = {'restricted', 'parking'}  # Usamos set para búsqueda más rápida

        for zone_name, zone_info in zone_data.items():
            if zone_name.lower() in target_zones and isinstance(zone_info, dict):
                coords = zone_info.get('coords')
                
                if isinstance(coords, list):
                    zones.append(zone_name)
                    
                    # Manejar tanto polígono único como lista de polígonos
                    polygons = coords if all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in coords[0]) else [coords]
                    
                    for poly in polygons:
                        if isinstance(poly, list) and len(poly) >= 3:
                            try:
                                # Convertir a tuplas de floats
                                processed_poly = []
                                for point in poly:
                                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                                        x = float(point[0])
                                        y = float(point[1])
                                        processed_poly.append((x, y))
                                
                                if len(processed_poly) >= 3:
                                    all_polygons.append(processed_poly)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Coordenadas inválidas en zona {zone_name}: {e}")
                                continue

        logger.debug(f"Zonas encontradas: {zones} | Polígonos válidos: {len(all_polygons)}")
        return zones, all_polygons

    except Exception as e:
        logger.error(f"Error procesando zone_restricted: {str(e)}")
        return [], []

def en_area_restringida_math(point, polygons):
    """Determina si el punto central está dentro de cualquier polígono restringido"""
    x, y = point
    for polygon in polygons:
        if point_in_polygon((x, y), polygon):
            return True
    return False

def get_central_detection_point(bbox, horizontal_offset=POINT_HORIZONTAL_OFFSET, vertical_position=POINT_VERTICAL_POSITION):
    """Genera un punto central de detección en posición relativa al bbox original"""
    try:
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        
        # Posición vertical (porcentaje desde la parte superior del bbox)
        y_pos = y1 + int(height * vertical_position)
        
        # Posición horizontal (POINT_HORIZONTAL_OFFSET ahora controla la posición central)
        # 0.5 = centro exacto, 0.0 = extremo izquierdo, 1.0 = extremo derecho
        x_pos = x1 + int(width * (0.5 + (horizontal_offset - 0.5)))
        
        # Asegurar que el punto esté dentro de los límites de la imagen
        central_point = (
            max(0, min(x_pos, CAMERA_RESOLUTION[0]-1)), 
            max(0, min(y_pos, CAMERA_RESOLUTION[1]-1))
        )
        
        return central_point
    except Exception as e:
        logger.error(f"Error calculando punto central de detección: {str(e)}")
        return ((x1 + x2) // 2, y2)  # Fallback a centro de la base

def procesamiento_coordenadas_sync(data, publish_callback):
    """Función principal de procesamiento - Versión corregida"""
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()

    try:
        # 1. Verificar primero si contiene las zonas requeridas
        zone_data = data.get(DATA_COORDS, {})
        if not isinstance(zone_data, dict):
            logger.debug(f"Cámara {cam_id} - Formato de zonas inválido, descartando")
            return
            
        # 2. Verificar presencia de zonas objetivo ANTES de procesar
        target_zones_present = any(
            zone.lower() in {'restricted', 'parking'} 
            for zone in zone_data.keys()
        )
        
        if not target_zones_present:
            logger.debug(f"Cámara {cam_id} - No contiene zonas 'restricted' o 'parking', descartando")
            return

        # 3. Parsear zonas y polígonos (solo si pasó el filtro anterior)
        zone_ids, polygons = parse_zones_and_polygons(zone_data)
        
        if not zone_ids:  # Verificación redundante por seguridad
            logger.debug(f"Cámara {cam_id} - No se encontraron zonas válidas después del parseo")
            return

        # 4. Crear estructura de zonas con sus polígonos
        zone_polygons = {
            zone_id: [polygon]  
            for zone_id, polygon in zip(zone_ids, polygons)
            if zone_id.lower() in {'restricted', 'parking'}  # Filtro adicional
        }

        # 5. Estructura de salida (solo si hay zonas válidas)
        output = {
            "camera_id": cam_id,
            "epoch_frame": data.get(DATA_EPOCH_FRAME, 0),
            "n_objects": data.get("n_objects", 0),
            "zone_restricted": zone_data,
            "object_dict": {}
        }

        # 6. Procesar cada objeto
        for category, objects in data.get(DATA_OBJETOS_DICT, {}).items():
            output["object_dict"][category] = []
            
            for obj in objects:
                # 6.1. Obtener coordenadas del bbox original
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                
                # 6.2. Obtener los puntos de detección
                detection_points = get_detection_points(coords)
                
                # 6.3. Verificar si alguno de los puntos está en zona restringida
                detected_zones = [
                    zone_id
                    for zone_id, polygons in zone_polygons.items()
                    if en_area_restringida_math(detection_points, polygons)
                ]

                alert = None
                tracking_id = obj.get(DATA_TRAKING_ID)

                if tracking_id and detected_zones:
                    if tracking_id not in vehicle_timers.get(cam_id, {}):
                        vehicle_timers.setdefault(cam_id, {})[tracking_id] = current_time
                        
                        alert = {
                            "type": "ingreso",
                            "message": f"Ingreso detectado en zona(s): {', '.join(detected_zones)}"
                        }

                        logger.info(f"INGRESO DETECTADO: {alert} ")
                        logger.info(f"TIEMPO PROCESAMIENTO OBJETO EN ZONA: {time.time() - start_time}s")

                    else:
                        elapsed = current_time - vehicle_timers[cam_id][tracking_id]
                        if elapsed > PERMANENCE_THRESHOLD:
                            vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer


                #logger.info(f"TIEMPO PROCESAMIENTO OBJETO: {time.time() - start_time}s")

                # 6.4. Construir objeto final
                output["object_dict"][category].append({
                    **obj,
                    "zones_interest": detected_zones,
                    "Alerta": alert
                })

        # 7. Publicar SOLO si hay zonas de interés válidas
        if zone_polygons:
            publish_callback(output)
            logger.info(f"Cámara {cam_id} - Publicado con {sum(len(v) for v in output['object_dict'].values())} objetos")
        else:
            logger.debug(f"Cámara {cam_id} - No contiene zonas válidas después de todos los filtros")

    except Exception as e:
        logger.error(f"Error en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Tiempo total: {time.time() - start_time}s")