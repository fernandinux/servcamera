import time
import math
from collections import defaultdict
from datetime import datetime
from config_logger import configurar_logger
from config import *

logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class VehicleDetector:
    def __init__(self, interval_minutes, distance_threshold, processing_time=30, sleep_time=5):
        """
        Inicializa el detector de vehículos abandonados
        
        Args:
            interval_minutes: Intervalo en minutos para comprobar vehículos abandonados
            distance_threshold: Umbral de distancia para considerar un vehículo en la misma posición
            processing_time: Tiempo en minutos que el sistema estará procesando
            sleep_time: Tiempo en minutos que el sistema estará en reposo
        """
        self.interval_sec = interval_minutes * 60
        self.distance_threshold = distance_threshold
        self.processing_time = processing_time * 60  # convertir a segundos
        self.sleep_time = sleep_time * 60  # convertir a segundos
        self.last_check = 0
        self.last_report = 0
        self.start_process_time = time.time()
        self.is_processing = True
        
        # Estructura: {camera_id: {vehicle_id: {"positions": [(centroid, timestamp)], "first_seen": timestamp}}}
        self.vehicle_registry = defaultdict(lambda: defaultdict(lambda: {"positions": [], "first_seen": 0}))
        
        # Vehículos que ya han sido reportados como abandonados
        self.reported_vehicles = set()
        
        # Categorías de vehículos a detectar
        self.vehicle_categories = VEHICLE_CATEGORIES

    def _get_all_vehicles(self, object_dict):
        """
        Extrae todos los vehículos del diccionario de objetos recibido
        
        Args:
            object_dict: Diccionario con objetos detectados por categoría
        
        Returns:
            Lista de vehículos con su tipo añadido
        """
        vehicles = []
        
        # Recorremos cada categoría de vehículo que esperamos
        for category_id, objects_list in object_dict.items():
            if category_id in self.vehicle_categories:
                for obj in objects_list:
                    # Añadimos el tipo de vehículo a cada objeto
                    obj['vehicle_type'] = self.vehicle_categories[category_id]
                    vehicles.append(obj)
        
        logger.debug(f"Extraídos {len(vehicles)} vehículos de las categorías de interés")
        return vehicles
    
    def _calc_centroid(self, coords):
        """
        Calcula el centroide de un objeto a partir de sus coordenadas
        
        Args:
            coords: Lista [x1, y1, x2, y2] con las coordenadas del bounding box
        
        Returns:
            Tupla (x, y) con el centroide
        """
        x1, y1, x2, y2 = coords
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    
    def _is_same_position(self, pos1, pos2):
        """
        Determina si dos posiciones son consideradas la misma
        
        Args:
            pos1: Primer centroide (x1, y1)
            pos2: Segundo centroide (x2, y2)
        
        Returns:
            Boolean indicando si están en la misma posición según el umbral
        """
        distance = math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        return distance <= self.distance_threshold
    
    def _should_process(self):
        """
        Determina si el sistema debe estar procesando o en reposo
        
        Returns:
            Boolean indicando si debe procesar
        """
        current_time = time.time()
        elapsed_time = current_time - self.start_process_time
        
        # Si está procesando y ha excedido el tiempo de procesamiento
        if self.is_processing and elapsed_time > self.processing_time:
            logger.info(f"Cambiando a modo reposo después de {self.processing_time//60} minutos de procesamiento")
            self.is_processing = False
            self.start_process_time = current_time
            return False
        
        # Si está en reposo y ha completado el tiempo de reposo
        elif not self.is_processing and elapsed_time > self.sleep_time:
            logger.info(f"Reactivando procesamiento después de {self.sleep_time//60} minutos de reposo")
            self.is_processing = True
            self.start_process_time = current_time
            return True
        
        # Mantener el estado actual
        return self.is_processing

    def _check_abandoned_time(self, positions, first_seen):
        """
        Verifica si un vehículo ha estado inmóvil durante suficiente tiempo
        
        Args:
            positions: Lista de posiciones con timestamps [(centroid, timestamp)]
            first_seen: Timestamp de cuando se vio por primera vez
        
        Returns:
            Tuple (is_abandoned, time_abandoned) - Boolean y tiempo en segundos
        """
        if not positions or len(positions) < 2:
            return False, 0
        
        current_time = time.time()
        
        # Si todas las posiciones son similares
        all_same_position = True
        first_position = positions[0][0]  # centroide de la primera posición
        
        for pos, _ in positions[1:]:
            if not self._is_same_position(first_position, pos):
                all_same_position = False
                break
        
        if all_same_position:
            # Calcular tiempo desde la primera vez que se vio
            time_abandoned = current_time - first_seen
            # Si supera el intervalo mínimo, considerar como abandonado
            if time_abandoned >= self.interval_sec:
                return True, time_abandoned
        
        return False, 0
    
    def _generate_report(self, camera_id):
        """
        Genera un reporte con todos los vehículos abandonados actualmente
        
        Args:
            camera_id: ID de la cámara
        
        Returns:
            Diccionario con el reporte de vehículos abandonados
        """
        current_time = time.time()
        abandoned_list = []
        
        # Verificar cada vehículo registrado
        for vehicle_id, data in self.vehicle_registry[camera_id].items():
            positions = data["positions"]
            first_seen = data["first_seen"]
            
            is_abandoned, time_abandoned = self._check_abandoned_time(positions, first_seen)
            
            if is_abandoned:
                # Obtener la última posición conocida
                last_position, _ = positions[-1]
                
                # Añadir al reporte si no ha sido reportado antes o si queremos reportes duplicados
                if vehicle_id not in self.reported_vehicles:
                    abandoned_list.append({
                        "id": vehicle_id,
                        "time_abandoned": int(time_abandoned),
                        "time_abandoned_human": self._format_time_duration(time_abandoned),
                        "last_position": last_position,
                        "first_seen": datetime.fromtimestamp(first_seen).strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                    # Marcar como reportado
                    self.reported_vehicles.add(vehicle_id)
        
        if abandoned_list:
            self.last_report = current_time
            return {
                "timestamp": int(current_time),
                "camera_id": camera_id,
                "report_time": datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S'),
                "abandoned_vehicles": abandoned_list,
                "total_abandoned": len(abandoned_list)
            }
        
        return None
    
    def _format_time_duration(self, seconds):
        """
        Formatea una duración en segundos a formato legible
        
        Args:
            seconds: Tiempo en segundos
            
        Returns:
            String con formato "X horas Y minutos Z segundos"
        """
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if hours > 0:
            parts.append(f"{hours} horas")
        if minutes > 0:
            parts.append(f"{minutes} minutos")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} segundos")
            
        return " ".join(parts)
    
    def _clean_old_records(self, max_age=3600):
        """
        Limpia registros antiguos para evitar crecimiento indefinido
        
        Args:
            max_age: Edad máxima en segundos antes de eliminar un registro
        """
        current_time = time.time()
        cameras_to_check = list(self.vehicle_registry.keys())
        
        for camera_id in cameras_to_check:
            vehicles_to_check = list(self.vehicle_registry[camera_id].keys())
            
            for vehicle_id in vehicles_to_check:
                positions = self.vehicle_registry[camera_id][vehicle_id]["positions"]
                
                if positions:
                    # Obtener el timestamp más reciente
                    _, latest_timestamp = positions[-1]
                    
                    # Si es muy antiguo, eliminar
                    if current_time - latest_timestamp > max_age:
                        logger.debug(f"Eliminando registro antiguo: cámara {camera_id}, vehículo {vehicle_id}")
                        del self.vehicle_registry[camera_id][vehicle_id]
                        
                        # También eliminar de reportados si está ahí
                        if vehicle_id in self.reported_vehicles:
                            self.reported_vehicles.remove(vehicle_id)
    
    def process(self, camera_id, object_dict):
        """
        Procesa los objetos detectados para identificar vehículos abandonados
        
        Args:
            camera_id: ID de la cámara
            object_dict: Diccionario con objetos detectados
            
        Returns:
            Lista de vehículos abandonados o None si no es momento de procesar
        """
        # Verificar si debemos procesar o estamos en reposo
        if not self._should_process():
            return None
        
        current_time = time.time()
        
        # Limpiar registros antiguos periódicamente (cada hora)
        if current_time - self.last_check > 3600:
            self._clean_old_records()
        
        # Obtener todos los vehículos detectados
        vehicles = self._get_all_vehicles(object_dict)
        logger.debug(f"Procesando {len(vehicles)} vehículos para cámara {camera_id}")
        
        # Actualizar registro de vehículos
        for vehicle in vehicles:
            # Usar id_tracking como identificador único
            obj_id = vehicle.get(DATA_TRAKING_ID)
            if not obj_id:
                logger.warning(f"Objeto sin ID de tracking, ignorando: {vehicle}")
                continue
                
            # Calcular centroide
            coords = vehicle.get(DATA_OBJETO_COORDENADAS)
            if not coords or len(coords) != 4:
                logger.warning(f"Coordenadas inválidas para objeto {obj_id}, ignorando")
                continue
                
            current_centroid = self._calc_centroid(coords)
            
            # Si es la primera vez que vemos este vehículo
            if not self.vehicle_registry[camera_id][obj_id]["positions"]:
                self.vehicle_registry[camera_id][obj_id]["first_seen"] = current_time
                
            # Añadir nueva posición
            self.vehicle_registry[camera_id][obj_id]["positions"].append((current_centroid, current_time))
            
            # Limitar número de posiciones guardadas (mantener últimas 10)
            if len(self.vehicle_registry[camera_id][obj_id]["positions"]) > 10:
                self.vehicle_registry[camera_id][obj_id]["positions"].pop(0)
        
        # Generar reporte si ha pasado suficiente tiempo desde el último
        if current_time - self.last_report > REPORT_INTERVAL_SEC:
            return self._generate_report(camera_id)
            
        self.last_check = current_time
        return None
    