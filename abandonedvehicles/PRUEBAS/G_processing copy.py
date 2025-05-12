import time
import math
from collections import defaultdict
from config_logger import configurar_logger
from config import *

logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class VehicleDetector:
    def __init__(self, interval_minutes=5, distance_threshold=15, execute_duration=3, tiempo_considerado_abandono = 10):
        self.interval_sec = interval_minutes * 60
        self.distance_threshold = distance_threshold
        self.execute_duration = execute_duration * 60
        self.last_check = 0
        self.tiempo_considerado_abandono = tiempo_considerado_abandono * 60
        self.vehicle_registry = defaultdict(dict)  # {camera: {id: (centroid, timestamp)}}

        # Categorías de vehículos a detectar (autos, motos, buses, etc.)
        self.vehicle_categories = VEHICLE_CATEGORIES

        logger.info(f"Inicializando VehicleDetector - Intervalo: {interval_minutes} min, "
                f"Umbral: {distance_threshold} px, "
                f"Duración de ejecución: {execute_duration} min, "
                f"Tiempo para considerar abandono: {tiempo_considerado_abandono} min")
        logger.info(f"Categorías de vehículos configuradas: {list(self.vehicle_categories.keys())}")

    def _get_all_vehicles(self, object_dict):
        """Filtra todos los objetos que son vehículos según las categorías definidas"""
        vehicles = []
        for category, type_name in self.vehicle_categories.items():
            category_objects = object_dict.get(category)
            if category_objects is not None:
                for obj in category_objects:
                    obj['vehicle_type'] = type_name  # Añadimos tipo al objeto
                vehicles.extend(category_objects)
                logger.info(f"Vehiculo de categoria {type_name} obtenido")
        return vehicles
    
    def _calc_centroid(self, coords):
        x1, y1, x2, y2 = coords
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def _is_same_position(self, pos1, pos2):
        distance = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
        return distance <= self.distance_threshold
    

    def process(self, camera_id, object_dict):
        current_time = time.time()

        if not self.last_check:
            self.last_check = time.time()
            logger.info("Inicializacion del last_check")
        
        # Verificar si es momento de procesar
        # if current_time - self.last_check < self.interval_sec:
        #     return []

        if current_time - self.last_check >= self.execute_duration:
            if current_time - (self.last_check + self.execute_duration) >= self.interval_sec:
                self.last_check = current_time

                logger.info(f"Ultimo irtervalo obtenido para camara {self.vehicle_registry[camera_id]}")
            
            else:
                return [] # 
            # time.sleep()
        
        logger.info(f"Iniciando verificación de intervalo ({self.interval_sec}s)")
        abandoned = []
        
        # Obtener TODOS los vehículos (de todas las categorías)
        vehicles = self._get_all_vehicles(object_dict)

        if self.vehicle_registry.get(camera_id) is None:      
            self.vehicle_registry[camera_id] = dict()
        
        for vehicle in vehicles:
            obj_id = vehicle[DATA_TRAKING_ID]
            current_centroid = self._calc_centroid(vehicle[DATA_OBJETO_COORDENADAS])

            prev_tiempo_abandonado = 0         
            prev_tiempo_procesado = current_time  
            
            if obj_id in self.vehicle_registry[camera_id]:
                prev_centroid, prev_tiempo_procesado, prev_tiempo_abandonado = self.vehicle_registry[camera_id][obj_id]
                if not self._is_same_position(prev_centroid, current_centroid):
                    prev_tiempo_abandonado = 0
                    prev_tiempo_procesado = current_time

            current_tiempo_abandonado = prev_tiempo_abandonado + (current_time - prev_tiempo_procesado)

            if current_tiempo_abandonado >= self.tiempo_considerado_abandono:
                    abandoned.append({
                        "id": obj_id,
                        "type": vehicle['vehicle_type'],
                        "coords": vehicle[DATA_OBJETO_COORDENADAS]
                    })

                    logger.info(f"DATOS DE OBJETOS IDENTIFICADOS COMO ABANDONDOS AGREGADOS PARA ENVIAR")
            
            self.vehicle_registry[camera_id][obj_id] = (current_centroid, current_time, current_tiempo_abandonado)
        
        self.last_check = current_time
        return abandoned