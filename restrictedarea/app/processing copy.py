import time
import numpy as np
import redis
import ast
import re
import json
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

def get_zones_from_redis(camera_id):
    """
    Obtiene las zonas desde Redis para una cámara específica usando la estructura hash
    
    Args:
        camera_id: ID de la cámara
    
    Returns:
        dict: Diccionario con las zonas de la cámara o {} si no existen
    """
    try:
        redis_conn = redis.Redis(connection_pool=redis_pool)
        
        # Obtenemos el valor del hash para esta cámara del contenedor "restricted_area"
        zone_data_str = redis_conn.hget(REDIS_ZONES_CONTAINER, camera_id)
        
        if not zone_data_str:
            logger.warning(f"No se encontraron zonas en Redis para la cámara {camera_id}")
            return {}
            
        # Convertir de string JSON a diccionario Python
        zone_data = json.loads(zone_data_str)
        logger.debug(f"Zonas obtenidas de Redis para cámara {camera_id}: {zone_data}")
        
        return zone_data
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar JSON de Redis para cámara {camera_id}: {str(e)}")
        return {}
    except Exception as e:
        logger.error(f"Error al obtener zonas desde Redis para cámara {camera_id}: {str(e)}")
        return {}

def parse_zones_and_polygons(zone_data, img_shape=None):
    """
    Procesa zone_restricted y convierte coordenadas relativas a absolutas
    Args:
        zone_data: Diccionario con las zonas
        img_shape: Tuple (height, width) de la imagen (NUEVO PARÁMETRO)
    Returns:
        (list) zonas válidas, (list) polígonos válidos en coordenadas absolutas
    """

    if not zone_data or not isinstance(zone_data, dict):
        return [], []

    try:
        zones = []
        all_polygons = []
        target_zones = {'restricted', 'parking'}  # Usamos set para búsqueda más rápida

        # NUEVA VALIDACIÓN: Verificar shape de imagen
        if img_shape is None or len(img_shape) < 2:
            logger.warning("No se proporcionó img_shape válido, usando valores por defecto 1080x1920")
            img_shape = (1080, 1920)  # Valor por defecto HD

        img_height, img_width = img_shape[0], img_shape[1]

        for zone_name, zone_info in zone_data.items():
            if zone_name.lower() in target_zones and isinstance(zone_info, dict):
                coords = zone_info.get('coords')
                
                if isinstance(coords, list):
                    zones.append(zone_name)
                    
                    if coords and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in coords[0]):
                        # Es una lista de polígonos (coords es [[[x,y],...], [[x,y],...]])
                        polygon_list = coords
                    else:
                        # Es un solo polígono (coords es [[x,y],...])
                        polygon_list = [coords]
                    
                    # Procesar cada polígono individualmente
                    for poly in polygon_list:
                        if isinstance(poly, list) and len(poly) >= 3:
                            absolute_poly = []
                            for point in poly:
                                if isinstance(point, (list, tuple)) and len(point) == 2:
                                    try:
                                        x_rel, y_rel = float(point[0]), float(point[1])
                                        # Conversión a coordenadas absolutas
                                        x_abs = x_rel * img_width
                                        y_abs = y_rel * img_height
                                        absolute_poly.append((x_abs, y_abs))
                                    except (ValueError, TypeError) as e:
                                        logger.warning(f"Punto inválido en zona {zone_name}: {point} - {str(e)}")
                                        continue
                            
                            # Validación de polígono mínimo (3 puntos)
                            if len(absolute_poly) >= 3:
                                all_polygons.append(absolute_poly)
                            else:
                                logger.warning(f"Polígono en zona {zone_name} no tiene suficientes puntos válidos")

        logger.debug(f"Zonas parseadas: {zones} | Polígonos válidos: {len(all_polygons)}")
        return zones, all_polygons

    except Exception as e:
        logger.error(f"Error parsing zone_restricted: {str(e)}")
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
    """Función principal de procesamiento - Versión modificada para obtener zonas desde Redis"""
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()

    try:
        # NUEVO: Obtener dimensiones de la imagen
        img_shape = data.get("shape", [1080, 1920])  # [height, width] por defecto HD
        if len(img_shape) >= 2:
            img_shape = (int(img_shape[0]), int(img_shape[1]))
        else:
            logger.warning(f"Cámara {cam_id} - shape inválido, usando 1080x1920")
            img_shape = (1080, 1920)
        
        # MODIFICADO: Obtener las zonas desde Redis en lugar del mensaje RabbitMQ
        zone_data = get_zones_from_redis(cam_id)
        
        if not isinstance(zone_data, dict):
            logger.debug(f"Cámara {cam_id} - Formato de zonas inválido en Redis, descartando")
            return
            
        # 2. Verificar presencia de zonas objetivo ANTES de procesar
        target_zones_present = any(
            zone.lower() in {'restricted', 'parking'} 
            for zone in zone_data.keys()
        )
        
        if not target_zones_present:
            logger.debug(f"Cámara {cam_id} - No contiene zonas 'restricted' o 'parking' en Redis, descartando")
            return

        # 3. Parsear zonas y polígonos (solo si pasó el filtro anterior)
        zone_ids, polygons = parse_zones_and_polygons(zone_data, img_shape=img_shape)
        
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
            "n_objects": 0,
            "zone_restricted": zone_data,  # Incluimos las zonas obtenidas de Redis
            "object_dict": {zone_id.lower(): [] for zone_id in zone_polygons}  # Solo zonas filtradas
        }

        total_objects_in_zones = 0

        # 6. Procesar cada objeto
        for category, objects in data.get(DATA_OBJETOS_DICT, {}).items():
            #output["object_dict"][category] = []
            
            for obj in objects:
                # 6.1. Obtener coordenadas del bbox original
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                
                # NUEVO: Validación adicional de coordenadas
                if len(coords) != 4 or any(not isinstance(c, (int, float)) for c in coords):
                    logger.warning(f"Objeto inválido en cámara {cam_id}: coordenadas malformadas")
                    continue
                
                # 6.2. Obtener los puntos de detección
                detection_points = get_central_detection_point(coords)
                
                # 6.3. Verificar si alguno de los puntos está en zona restringida
                detected_zones = [
                    zone_id
                    for zone_id, zone_polygons in {
                        z_id: [poly] for z_id, poly in zip(zone_ids, polygons)
                    }.items()
                    if en_area_restringida_math(detection_points, zone_polygons)
                ]

                # Solo procesar si está en al menos una zona
                if detected_zones:
                    total_objects_in_zones += 1
                    zone_key = detected_zones[0].lower()  # Usamos la primera zona como categoría
                
                    # Lógica de alertas
                    alert = None
                    tracking_id = obj.get(DATA_TRAKING_ID)

                    if tracking_id:
                        if tracking_id not in vehicle_timers.get(cam_id, {}):
                            vehicle_timers.setdefault(cam_id, {})[tracking_id] = current_time
                            
                            alert = {
                                "type": "Ingreso",
                                "message": f"Ingreso detectado en zona(s): {', '.join(detected_zones)}"
                            }

                            logger.info(f"INGRESO DETECTADO: {alert} ")

                        else:
                            elapsed = current_time - vehicle_timers[cam_id][tracking_id]
                            if elapsed > PERMANENCE_THRESHOLD:
                                vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer
                                logger.info(f"PERMANENCIA DETECTADA")
                
                    # 6.4. Construir objeto final
                    output["object_dict"][zone_key].append({
                        **{k: v for k, v in obj.items() if k != DATA_OBJETO_COORDENADAS},
                        "coords": coords,
                    })

        # Actualizar conteo real de objetos
        output["n_objects"] = total_objects_in_zones           

        # 7. Publicar SOLO si hay zonas de interés válidas
        publish_callback(output)

        if total_objects_in_zones > 0:
            logger.info(f"Cámara {cam_id} - Publicados {total_objects_in_zones} objetos en zonas")

        else:
            logger.info(f"Cámara {cam_id} - Zonas vacías publicadas")

    except Exception as e:
        logger.error(f"Error en cámara {cam_id}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"Tiempo total: {time.time() - start_time}s")