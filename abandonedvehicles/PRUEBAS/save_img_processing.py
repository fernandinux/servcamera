import time
import numpy as np
import cv2
import json
import ast
import re
import redis
from PIL import Image
import os
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

# Configuración para guardar imágenes
os.makedirs(DEBUG_IMG_DIR, exist_ok=True)

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

def dibujar_visualizacion(frame, polygons, tracking_id, bbox, adjusted_coords):
    """Dibuja las detecciones en el frame"""
    try:
        # Dibujar área restringida
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        for poligono in polygons:
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [puntos], color=255)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(frame, contours, -1, (0, 0, 255), 2)
        
        # Dibujar bounding box completo (verde)
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Dibujar zona de detección (parte inferior - azul)
        adj_x1, adj_y1, adj_x2, adj_y2 = adjusted_coords
        cv2.rectangle(frame, (adj_x1, adj_y1), (adj_x2, adj_y2), (255, 0, 0), 2)
        
        # Añadir texto
        cv2.putText(frame, f"ID: {tracking_id}", (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        return frame
    except Exception as e:
        logger.error(f"Error al dibujar visualización: {str(e)}")
        return frame

def parse_polygons(zone_restricted_str):
    """Versión mejorada basada en parse_zones_and_polygons del otro proyecto"""
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
            # Filtrar solo la zona '10'
            if '10' in data:
                polygons = data['10']
                if isinstance(polygons, list):
                    zones.append('10')
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
    """Versión mejorada con manejo robusto de polígonos"""
    mask = np.zeros(resolution, dtype=np.uint8)

    for poligono in restringidas:
        try:
            # Conversión robusta a formato numpy que OpenCV espera
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [puntos], color=255)
        except Exception as e:
            logger.error(f"Error dibujando polígono {poligono}: {str(e)}")    
    return mask

def en_area_restringida(bbox, mask):
    """Verifica si una bbox está dentro del área restringida"""
    try:
        x1, y1, x2, y2 = bbox
        # Asegurar que las coordenadas estén dentro de los límites de la imagen
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(mask.shape[1], x2), min(mask.shape[0], y2)
        
        if x1 >= x2 or y1 >= y2:  # Bbox inválida
            return False
            
        roi = mask[y1:y2, x1:x2]
        return cv2.countNonZero(roi) > 0
    except Exception as e:
        logger.error(f"Error verificando área restringida: {str(e)}")
        return False

def adjust_coords_for_lower_part(vehicle_coords, lower_percentage=MASK_LOWER_PERCENTAGE):
    """Ajusta las coordenadas para considerar solo la parte inferior del vehículo"""
    try:
        x1, y1, x2, y2 = vehicle_coords
        height = y2 - y1
        y1_adjusted = y2 - int(height * lower_percentage)
        y1_adjusted = max(y1_adjusted, 0)
        y2 = min(y2, CAMERA_RESOLUTION[1])
        return (x1, y1_adjusted, x2, y2)
    except Exception as e:
        logger.error(f"Error ajustando coordenadas: {str(e)}")
        return vehicle_coords

def procesamiento_coordenadas(data, publish_callback):
    """Función principal de procesamiento con visualización mejorada"""
    start_time = time.time()
    cam_id = data.get(DATA_CAMERA, "unknown")
    current_time = time.time()
    
    # Verificación adicional (aunque ya se filtró en el consumer)
    if "'10'" not in str(data.get(DATA_COORDS, "")):
        logger.debug(f"Cámara {cam_id} - No contiene zona 10, ignorando")
        return

    try:
        # 1. Parsear zonas y polígonos
        _, polygons = parse_polygons(data.get(DATA_COORDS, ""))
        
        if not polygons:
            logger.debug(f"Cámara {cam_id} - Sin polígonos definidos")
            return

        # 2. Crear máscara combinada de todas las zonas
        mask = crear_mascara_area(polygons, CAMERA_RESOLUTION[::-1])
        
        # 3. Obtener frame original para visualización
        frame = get_frame_from_redis(data) if SAVE_DETECTION_IMAGES else None
        
        # 4. Inicializar estructura de vehículos por cámara
        if cam_id not in vehicle_timers:
            vehicle_timers[cam_id] = {}

        # 5. Procesar cada categoría de objetos
        for categoria, objetos in data.get(DATA_OBJETOS_DICT, {}).items():
            for obj in objetos:
                tracking_id = obj.get(DATA_TRAKING_ID)
                if not tracking_id:
                    continue
                
                # 6. Verificar si está en área restringida
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                adjusted_coords = adjust_coords_for_lower_part(coords)
                
                if en_area_restringida(adjusted_coords, mask):
                    # Manejo de alertas de ingreso
                    if tracking_id not in vehicle_timers[cam_id]:
                        vehicle_timers[cam_id][tracking_id] = current_time
                        
                        # Guardar imagen con anotaciones si está configurado
                        if frame is not None:
                            frame_annotated = dibujar_visualizacion(
                                frame.copy(), 
                                polygons, 
                                tracking_id, 
                                coords, 
                                adjusted_coords
                            )
                            guardar_imagen(frame_annotated, tracking_id)
                        
                        alert = {
                            'camera_id': cam_id,
                            'category': 1,
                            'message': 'Vehículo detectado en área restringida',
                            'type': 1,
                            'sub_type': 1,
                            'epoch_object': obj.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                            'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                            'object_id': obj.get(DATA_OBJETO_ID_CONCATENADO, 0),
                            'n_objects': data.get(DATA_N_OBJECTOS, 0),
                            'id_tracking': tracking_id,
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
                                'sub_type': 2,
                                'epoch_object': obj.get(DATA_OBJETO_EPOCH_OBJECT, 0),
                                'epoch_frame': data.get(DATA_EPOCH_FRAME, 0),
                                'object_id': obj.get(DATA_OBJETO_ID_CONCATENADO, 0),
                                'n_objects': data.get(DATA_N_OBJECTOS, 0),
                                'id_tracking': tracking_id,
                                'zone_restricted': data.get(DATA_COORDS, 0)
                            }
                            publish_callback(alert)
                            vehicle_timers[cam_id][tracking_id] = current_time  # Reset timer
                
                else:
                    # Limpiar timer si el vehículo salió del área
                    if tracking_id in vehicle_timers.get(cam_id, {}):
                        del vehicle_timers[cam_id][tracking_id]

    except Exception as e:
        logger.error(f"Error en procesamiento_coordenadas (cámara {cam_id}): {str(e)}")
    finally:
        logger.info(f"Tiempo total del proceso (cámara {cam_id}): {time.time() - start_time:.4f} segundos")