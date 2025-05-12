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

# Parámetros ajustables para la posición de los puntos de detección
POINT_HORIZONTAL_OFFSET = 0.2  # 20% desde los bordes horizontales
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

def parse_zones_and_polygons(zone_restricted_str):
    """Parsea los polígonos de zonas restringidas desde un string JSON"""
    start_time = time.time()
    if not zone_restricted_str or str(zone_restricted_str).strip().lower() in ('none', '{}', '[]'):
        logger.debug(f"Parseo de zonas completado en {time.time() - start_time:.6f}s (sin polígonos)")
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
        
        logger.debug(f"Parseo de zonas completado en {time.time() - start_time:.6f}s | {len(all_polygons)} polígonos")
        return zones, all_polygons
    
    except Exception as e:
        logger.error(f"Error parsing zone_restricted (input: {zone_restricted_str[:50]}...): {str(e)}")
        return [], []

def en_area_restringida_math(points, polygons):
    """Determina si ALGÚN punto está dentro de cualquier polígono restringido"""
    start_time = time.time()
    result = False
    for (x, y) in points:
        for polygon in polygons:
            if point_in_polygon((x, y), polygon):
                result = True
                break
        if result:
            break
    
    logger.debug(f"Verificación en área restringida: {time.time() - start_time:.6f}s")
    return result

def get_detection_points(bbox, horizontal_offset=POINT_HORIZONTAL_OFFSET, vertical_position=POINT_VERTICAL_POSITION):
    """Genera dos puntos de detección en posición relativa al bbox original"""
    start_time = time.time()
    try:
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        
        # Posición vertical (porcentaje desde la parte superior del bbox)
        y_pos = y1 + int(height * vertical_position)
        
        # Punto izquierdo (offset desde el borde izquierdo)
        left_x = x1 + int(width * horizontal_offset)
        left_point = (left_x, y_pos)
        
        # Punto derecho (offset desde el borde derecho)
        right_x = x2 - int(width * horizontal_offset)
        right_point = (right_x, y_pos)
        
        # Asegurar que los puntos estén dentro de los límites de la imagen
        left_point = (
            max(0, min(left_x, CAMERA_RESOLUTION[0]-1)), 
            max(0, min(y_pos, CAMERA_RESOLUTION[1]-1))
        )
        right_point = (
            max(0, min(right_x, CAMERA_RESOLUTION[0]-1)), 
            max(0, min(y_pos, CAMERA_RESOLUTION[1]-1))
        )
        
        logger.debug(f"Generación de puntos de detección: {time.time() - start_time:.6f}s")
        return [left_point, right_point]
    except Exception as e:
        logger.error(f"Error calculando puntos de detección: {str(e)}")
        return [(x1, y2), (x2, y2)]  # Fallback a esquinas inferiores

def procesamiento_coordenadas_sync(data, publish_callback):
    """Función principal de procesamiento"""
    frame_start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()

    try:
        # 1. Parsear zonas y polígonos
        parse_start = time.time()
        zone_ids, polygons = parse_zones_and_polygons(data.get(DATA_COORDS, ""))
        logger.info(f"Cámara {cam_id} - Parseo de zonas: {time.time() - parse_start:.6f}s")
        
        if not polygons:
            logger.debug(f"Cámara {cam_id} - Sin polígonos definidos, descartando")
            return
        
        # 2. Crear estructura de zonas con sus polígonos
        struct_start = time.time()
        zone_polygons = {
            zone_id: [polygon]  # Lista de polígonos por zona
            for zone_id, polygon in zip(zone_ids, polygons)
        }
        logger.debug(f"Cámara {cam_id} - Creación estructura zonas: {time.time() - struct_start:.6f}s")

        # 3. Estructura de salida
        output = {
            "camera_id": cam_id,
            "epoch_frame": data.get(DATA_EPOCH_FRAME, 0),
            "n_objects": data.get("n_objects", 0),
            "zone_restricted": data.get(DATA_COORDS, ""),
            "object_dict": {},
            "metrics": {
                "total_objects": 0,
                "total_processing_time": 0,
                "avg_time_per_object": 0
            }
        }

        # 4. Procesar cada objeto
        obj_processing_times = []
        for category, objects in data.get(DATA_OBJETOS_DICT, {}).items():
            output["object_dict"][category] = []
            
            for obj in objects:
                obj_start_time = time.time()
                
                # 4.1. Obtener coordenadas del bbox original
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                
                # 4.2. Obtener los puntos de detección
                points_start = time.time()
                detection_points = get_detection_points(coords)
                points_time = time.time() - points_start
                
                # 4.3. Verificar si está en zona restringida
                zone_start = time.time()
                detected_zones = [
                    zone_id
                    for zone_id, polygons in zone_polygons.items()
                    if en_area_restringida_math(detection_points, polygons)
                ]
                zone_time = time.time() - zone_start

                # 4.4. Lógica de alertas
                alert_start = time.time()
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
                                "message": f"Superó Umbral de permanencia de {elapsed:.1f}s en zona(s): {', '.join(detected_zones)}"
                            }
                            vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer
                alert_time = time.time() - alert_start

                # 4.5. Construir objeto final
                obj["zones_interest"] = detected_zones
                obj["Alerta"] = alert
                output["object_dict"][category].append(obj)
                
                # Registrar métricas del objeto
                obj_time = time.time() - obj_start_time
                obj_processing_times.append(obj_time)
                logger.debug(
                    f"Objeto procesado en {obj_time:.6f}s | "
                    f"Puntos: {points_time:.6f}s | "
                    f"Zonas: {zone_time:.6f}s | "
                    f"Alertas: {alert_time:.6f}s"
                )

        # Calcular métricas agregadas
        if obj_processing_times:
            output["metrics"]["total_objects"] = len(obj_processing_times)
            output["metrics"]["total_processing_time"] = sum(obj_processing_times)
            output["metrics"]["avg_time_per_object"] = sum(obj_processing_times) / len(obj_processing_times)

        # Publicar resultados
        publish_start = time.time()
        publish_callback(output)
        logger.debug(f"Publicación de resultados: {time.time() - publish_start:.6f}s")

        # Log resumen del frame
        frame_time = time.time() - frame_start_time
        logger.info(
            f"Cámara {cam_id} - Frame procesado en {frame_time:.6f}s | "
            f"{len(obj_processing_times)} objetos | "
            f"Tiempo promedio por objeto: {output['metrics']['avg_time_per_object']:.6f}s"
        )

    except Exception as e:
        logger.error(f"Error en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Cámara {cam_id} - Tiempo total de procesamiento: {time.time() - frame_start_time:.6f}s")