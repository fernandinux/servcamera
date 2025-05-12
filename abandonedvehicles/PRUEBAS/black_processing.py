import time
import numpy as np
import cv2
import json
import ast
import re
import os
from config import *
from config_logger import configurar_logger

logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Diccionario para almacenar el tiempo de entrada
vehicle_timers = {}

# Crear carpeta para imágenes procesadas
OUTPUT_FOLDER = "output_images"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

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

def save_processed_image(cam_id, frame, timestamp):
    """Guarda la imagen procesada en la carpeta de salida."""
    filename = os.path.join(OUTPUT_FOLDER, f"{cam_id}_{timestamp}.jpg")
    cv2.imwrite(filename, frame)
    logger.info(f"Imagen guardada: {filename}")


def procesamiento_coordenadas(data, publish_callback):
    """Función principal de procesamiento manteniendo tu formato de alerta"""
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

        # 3. Crear frame en blanco para visualización
        frame = np.zeros((CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), dtype=np.uint8)
        
        # Dibujar las áreas restringidas en la imagen
        for poligono in polygons:
            puntos = np.array(poligono, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [puntos], isClosed=True, color=(0, 0, 255), thickness=2)


        # 3. Inicializar estructura de vehículos por cámara
        if cam_id not in vehicle_timers:
            vehicle_timers[cam_id] = {}

        # 4. Procesar cada categoría de objetos
        for categoria, objetos in data.get(DATA_OBJETOS_DICT, {}).items():
            for obj in objetos:
                tracking_id = obj.get(DATA_TRAKING_ID)
                if not tracking_id:
                    continue
                
                # 5. Verificar si está en área restringida
                coords = obj.get(DATA_OBJETO_COORDENADAS, (0, 0, 0, 0))
                adjusted_coords = adjust_coords_for_lower_part(coords)
                
                color = (0, 255, 0)  # Verde por defecto
                if en_area_restringida(adjusted_coords, mask):
                    color = (0, 0, 255)  # Rojo si está en área restringida

                if en_area_restringida(adjusted_coords, mask):
                    # Manejo de alertas de ingreso
                    if tracking_id not in vehicle_timers[cam_id]:
                        vehicle_timers[cam_id][tracking_id] = current_time
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


                # Dibujar bounding box en la imagen
                x1, y1, x2, y2 = adjusted_coords
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"ID {tracking_id}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)  
                 
        # Guardar imagen procesada
        save_processed_image(cam_id, frame, current_time)

    except Exception as e:
        logger.error(f"Error en procesamiento_coordenadas (cámara {cam_id}): {str(e)}")
    finally:
        logger.info(f"Tiempo total del proceso (cámara {cam_id}): {time.time() - start_time:.4f} segundos")