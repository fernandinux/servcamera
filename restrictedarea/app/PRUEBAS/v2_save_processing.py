import time
from config import *
from config_logger import configurar_logger
import numpy as np
import cv2
import redis
import ast
import os
from PIL import Image
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

# Configuración para guardar imágenes
os.makedirs(DEBUG_IMG_DIR, exist_ok=True)

def parse_polygons(zone_restricted_str):
    """
    Versión robusta que maneja:
    - Cámara 27: {"1": [poligono1, poligono2]} → Extrae ambos polígonos.
    - Cámara 35: {"21": [poligono1]} → Extrae un polígono.
    """
    try:
        data = ast.literal_eval(zone_restricted_str.replace("'", '"'))
        polygons = []
        
        if isinstance(data, dict):
            for zone_id, zone_data in data.items():
                if isinstance(zone_data, list):
                    # Si es lista de listas (como en cámara 27)
                    if all(isinstance(p, list) for p in zone_data):
                        polygons.extend(zone_data)
                    # Si es lista directa de puntos (backward compatibility)
                    else:
                        polygons.append(zone_data)
        
        # Debug: Verifica los polígonos crudos
        logger.debug(f"Polígonos crudos extraídos: {polygons}")
        
        # Conversión a coordenadas válidas
        parsed_polygons = []
        for polygon in polygons:
            parsed_points = []
            for point in polygon:
                if isinstance(point, str):
                    match = re.match(r'\((\d+),\s*(\d+)\)', point.strip())
                    if match:
                        parsed_points.append((int(match.group(1)), int(match.group(2))))
                    else:
                        raise ValueError(f"Formato de punto inválido: {point}")
                elif isinstance(point, (list, tuple)):
                    parsed_points.append((int(point[0]), int(point[1])))
                else:
                    raise ValueError(f"Tipo de punto no soportado: {type(point)}")
            
            if len(parsed_points) >= 3:
                parsed_polygons.append(parsed_points)
                # Debug: Verifica puntos convertidos
                logger.debug(f"Polígono convertido: {parsed_points}")
            else:
                logger.warning(f"Polígono descartado (menos de 3 puntos): {polygon}")
        
        return parsed_polygons
    
    except Exception as e:
        logger.error(f"Error parseando polígonos: {str(e)}")
        return []


def crear_mascara_area(poligonos, resolution):
    mask = np.zeros(resolution, dtype=np.uint8)
    for poligono in poligonos:
        try:
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [puntos], color=255, lineType=cv2.LINE_AA)
        except Exception as e:
            logger.error(f"Error dibujando polígono {poligono}: {str(e)}")
    return mask

def en_area_restringida(bbox, mask):
    x1, y1, x2, y2 = bbox
    roi = mask[y1:y2, x1:x2]
    return cv2.countNonZero(roi) > 0

def check_if_in_restricted_area(cam_id, coords, mask):
    """
    Verifica si un vehículo está dentro de la zona restringida poligonal.
    """
    return en_area_restringida(coords, mask)

def dibujar_visualizacion(frame, data, poligonos, tracking_id, bbox):
    try:
        cam_id = data[DATA_CAMERA]
        colors = [(0, 0, 255), (0, 255, 0)]  # Rojo y Verde
        
        # Debug: Verifica los polígonos recibidos
        logger.info(f"Cámara {cam_id} - Número de polígonos a dibujar: {len(poligonos)}")
        
        for i, poligono in enumerate(poligonos):
            # Debug: Verifica coordenadas del polígono actual
            logger.info(f"Polígono {i+1}: {poligono}")
            
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(
                frame, 
                [puntos], 
                isClosed=True, 
                color=colors[i % len(colors)], 
                thickness=2
            )
            
            # Dibuja el centroide para verificar posición
            centroide = np.mean(puntos, axis=0).astype(int)[0]
            cv2.circle(frame, tuple(centroide), 5, colors[i % len(colors)], -1)
            cv2.putText(
                frame, 
                f"Zona {i+1}", 
                tuple(centroide), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                colors[i % len(colors)], 
                2
            )

        # Dibuja bounding boxes (igual que antes)
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Bbox completo (verde)
        
        adj_coords = adjust_coords_for_lower_part(bbox)
        adj_x1, adj_y1, adj_x2, adj_y2 = adj_coords
        cv2.rectangle(frame, (adj_x1, adj_y1), (adj_x2, adj_y2), (255, 0, 0), 2)  # Zona detección (azul)
        
        return frame
    except Exception as e:
        logger.error(f"Error dibujando en cámara {cam_id}: {str(e)}")
        return frame

def guardar_imagen(frame, tracking_id):
    """Guarda la imagen con las anotaciones"""
    if not SAVE_DETECTION_IMAGES or frame is None:
        return
    
    try:
        # Convertir a RGB (Pillow usa este formato)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(frame_rgb)
        
        filename = f"{DEBUG_IMG_DIR}/{tracking_id}_{int(time.time())}.jpg"
        img_pil.save(filename, quality=IMAGE_QUALITY)
        logger.info(f"Imagen guardada: {filename}")
    except Exception as e:
        logger.error(f"Error al guardar imagen: {str(e)}")

def adjust_coords_for_lower_part(vehicle_coords, lower_percentage=MASK_LOWER_PERCENTAGE):
    x1, y1, x2, y2 = vehicle_coords
    height = y2 - y1
    y1_adjusted = y2 - int(height * lower_percentage)
    y1_adjusted = max(y1_adjusted, 0)
    y2 = min(y2, CAMERA_RESOLUTION[1])
    return (x1, y1_adjusted, x2, y2)

def get_points_from_camera_id(data, cam_id):
    try:
        zone_restricted_str = data[DATA_COORDS]
        return parse_polygons(zone_restricted_str)  # Usa la nueva función parser
    except Exception as e:
        logger.error(f"Error obteniendo polígonos: {str(e)}")
        return []

def get_frame_from_redis(data):
    """Obtiene el frame original desde Redis"""
    try:
        r = redis.Redis(connection_pool=redis_pool, decode_responses=False)
        image_bytes = r.get(f"{data[DATA_CAMERA]}{data[DATA_EPOCH_FRAME]}")
        
        if not image_bytes:
            logger.error(f"Frame {data[DATA_EPOCH_FRAME]} no existe en Redis")
            return None
            
        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        logger.error(f"Error al obtener frame de Redis: {str(e)}")
        return None

def procesamiento_coordenadas(data, publish_callback):
    start_time = time.time()
    cam_id = data[DATA_CAMERA]
    current_time = time.time()
    logger.info(f"Procesando datos de la cámara {cam_id}")

    try:
        RESTRICTED_AREAS_BY_CAMERA_ID = get_points_from_camera_id(data, cam_id)
        mask = crear_mascara_area(RESTRICTED_AREAS_BY_CAMERA_ID, CAMERA_RESOLUTION[::-1])
        
        # Obtener frame original para visualización
        frame = get_frame_from_redis(data)
        
        if DATA_OBJETOS_DICT not in data:
            logger.error(f"Campo '{DATA_OBJETOS_DICT}' no encontrado en datos")
            return
            
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
                    # Solo generar imagen si es una nueva detección
                    if tracking_id not in vehicle_timers[cam_id] and frame is not None:
                        frame_annotated = dibujar_visualizacion(
                            frame.copy(), 
                            data, 
                            RESTRICTED_AREAS_BY_CAMERA_ID, 
                            tracking_id, 
                            new_coords
                        )
                        guardar_imagen(frame_annotated, tracking_id)
                    
                    # Resto de la lógica de alertas
                    if tracking_id not in vehicle_timers[cam_id]:
                        vehicle_timers[cam_id][tracking_id] = current_time
                        alert = {
                            'camera_id': cam_id,
                            'category': 1,
                            'message': 'Vehículo detectado en área restringida',
                            'type': 1,
                            'sub_type': 1,
                            'epoch_object': new_box.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                            'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                            'object_id': new_box.get(DATA_OBJETO_ID_CONCATENADO, 0),
                            'n_objects': data.get(DATA_N_OBJECTOS, 0),
                            'object_dict': data.get(DATA_OBJETOS_DICT, 0),
                            'id_tracking': new_box.get(DATA_TRAKING_ID, 0),
                            'zone_restricted': data.get(DATA_COORDS, 0)
                        }
                        publish_callback(alert)
                    else:
                        elapsed_time = current_time - vehicle_timers[cam_id][tracking_id]
                        if elapsed_time > PERMANENCE_THRESHOLD:
                            alert = {
                                'camera_id': cam_id,
                                'category': 1,
                                'message': f'Permanencia de Vehículo: {elapsed_time:.2f}s',
                                'type': 1,
                                'sub_type': 2,
                                'epoch_object': new_box.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                                'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                                'object_id': new_box.get(DATA_OBJETO_ID_CONCATENADO, 0),
                                'n_objects': data.get(DATA_N_OBJECTOS, 0),
                                'object_dict': data.get(DATA_OBJETOS_DICT, 0),
                                'id_tracking': new_box.get(DATA_TRAKING_ID, 0),
                                'zone_restricted': data.get(DATA_COORDS, 0)
                            }
                            publish_callback(alert)
                            vehicle_timers[cam_id][tracking_id] = current_time
                else:
                    if cam_id in vehicle_timers and tracking_id in vehicle_timers[cam_id]:
                        del vehicle_timers[cam_id][tracking_id]

    except Exception as e:
        logger.error(f"Error en procesamiento: {str(e)}")

    elapsed_time = time.time() - start_time
    logger.info(f"Tiempo total del proceso: {elapsed_time} segundos")