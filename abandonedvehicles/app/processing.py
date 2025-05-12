import time
import math
import json
from collections import defaultdict
from config_logger import configurar_logger
from config import *
from redis_manager import RedisManager

logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class VehicleDetector:
    def __init__(self, interval_minutes=300, distance_threshold=30, execute_duration=5, 
                 tiempo_considerado_abandono=72, similarity_threshold=0.85,
                 deduplication_window=5):
        self.interval_sec = interval_minutes * 60
        self.distance_threshold = distance_threshold
        self.execute_duration = execute_duration * 60
         # Multiplicamos por 3600 (60*60) para convertir horas a segundos
        self.tiempo_considerado_abandono = tiempo_considerado_abandono * 3600
        self.last_check = 0

        #Inicializar el gestor de REDIS
        self.redis_manager = RedisManager()

         # Cargar el registro de vehículos desde Redis (todas las cámaras)
        self.vehicle_registry = self.redis_manager.load_all_cameras_data()

        # Control de deduplicación
        self.similarity_threshold = similarity_threshold
        self.deduplication_window = deduplication_window
        self.recent_abandoned_reports = defaultdict(list)

        # Categorías de vehículos a detectar
        self.vehicle_categories = VEHICLE_CATEGORIES

        logger.info(f"Inicializando VehicleDetector mejorado - Intervalo: {interval_minutes} min, "
                  f"Umbral: {distance_threshold} px, "
                  f"Duración de ejecución: {execute_duration} min, "
                  f"Tiempo para considerar abandono: {tiempo_considerado_abandono} horas")
        logger.info(f"Categorías de vehículos configuradas: {list(self.vehicle_categories.keys())}")

        cameras_loaded = len(self.vehicle_registry)
        total_vehicles = sum(len(vehicles) for vehicles in self.vehicle_registry.values())
        logger.info(f"Cargados datos de {cameras_loaded} cámaras con {total_vehicles} vehículos desde Redis")


    def _get_all_vehicles(self, object_dict):
        """Filtra todos los objetos que son vehículos según las categorías definidas"""
        vehicles = []
        for category, type_name in self.vehicle_categories.items():
            category_objects = object_dict.get(category)
            if category_objects is not None:
                for obj in category_objects:
                    obj['vehicle_type'] = type_name
                vehicles.extend(category_objects)
                logger.debug(f"Vehículo de categoría {type_name} obtenido")
        return vehicles
    
    def _calc_centroid(self, coords):
        """Calcula el centroide de un objeto basado en sus coordenadas"""
        x1, y1, x2, y2 = coords
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def _is_same_position(self, pos1, pos2):
        """Determina si dos posiciones son consideradas la misma basado en la distancia"""
        distance = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
        return distance <= self.distance_threshold

    def _calc_similarity_score(self, coord1, coord2, centroid1, centroid2):
        """
        Calcula un puntaje de similitud entre dos detecciones
        """
        # Calcular distancia entre centroides
        distance = math.sqrt((centroid1[0]-centroid2[0])**2 + (centroid1[1]-centroid2[1])**2)
        
        # Calcular áreas
        x1a, y1a, x2a, y2a = coord1
        x1b, y1b, x2b, y2b = coord2
        area1 = (x2a - x1a) * (y2a - y1a)
        area2 = (x2b - x1b) * (y2b - y1b)
        
        # Calcular diferencia de área normalizada
        area_diff = abs(area1 - area2) / max(area1, area2) if max(area1, area2) > 0 else 0
        
        # Calcular puntaje compuesto
        max_distance = 20  # Distancia máxima a considerar
        distance_score = max(0, 1 - (distance / max_distance)) if max_distance > 0 else 0
        area_score = 1 - area_diff
        
        # Puntaje final (70% basado en distancia, 30% en similitud de área)
        final_score = (0.7 * distance_score) + (0.3 * area_score)
        
        return final_score

    def _find_matching_vehicle(self, camera_id, current_id, coords, centroid):
        """
        Busca si hay un vehículo en el registro que coincida con las coordenadas actuales,
        incluso si tiene un ID diferente. Esto es crucial para mantener el seguimiento entre ciclos.
        
        Returns:
            str: ID del vehículo coincidente o None si no hay coincidencia
        """
        if camera_id not in self.vehicle_registry:
            return None
            
        # Primero verificamos si el ID actual existe en el registro
        if current_id in self.vehicle_registry[camera_id]:
            stored_centroid = self.vehicle_registry[camera_id][current_id]["centroid"]
            if self._is_same_position(stored_centroid, centroid):
                return current_id
        
        # Si no existe o no coincide por posición, buscamos por similitud
        best_match = None
        best_score = 0
        
        for vehicle_id, vehicle_data in self.vehicle_registry[camera_id].items():
            stored_centroid = vehicle_data["centroid"]
            stored_coords = vehicle_data["coords"]
            
            similarity = self._calc_similarity_score(coords, stored_coords, centroid, stored_centroid)
            
            if similarity > self.similarity_threshold and similarity > best_score:
                best_score = similarity
                best_match = vehicle_id
        
        if best_match:
            logger.debug(f"Vehículo con ID={current_id} coincide con vehículo previamente registrado ID={best_match} (score={best_score:.2f})")
        
        return best_match

    def _clean_old_reports(self, camera_id, current_time):
        """Limpia informes antiguos fuera de la ventana de deduplicación"""
        if camera_id not in self.recent_abandoned_reports:
            return
            
        self.recent_abandoned_reports[camera_id] = [
            report for report in self.recent_abandoned_reports[camera_id]
            if current_time - report[1] <= self.deduplication_window
        ]
    
    def _is_duplicate_report(self, camera_id, vehicle_id, centroid, coords, current_time):
        """Determina si este informe es un duplicado de uno reciente"""
        if camera_id not in self.recent_abandoned_reports:
            return False
            
        for report_id, report_time, report_coords in self.recent_abandoned_reports[camera_id]:
            if report_id == vehicle_id and current_time - report_time <= self.deduplication_window:
                return True
                
            report_centroid = self._calc_centroid(report_coords)
            similarity = self._calc_similarity_score(coords, report_coords, centroid, report_centroid)
            
            if similarity >= self.similarity_threshold:
                logger.debug(f"Detección similar a informe reciente: ID actual={vehicle_id}, ID previo={report_id}, "
                            f"Similitud={similarity:.2f}")
                return True
                
        return False

    def is_active(self):
        """Determina si el detector está en estado activo o inactivo"""
        if not self.last_check:
            return True
        
        current_time = time.time()
        elapsed_time = current_time - self.last_check
        
        cycle_duration = self.execute_duration + self.interval_sec
        position_in_cycle = elapsed_time % cycle_duration
        
        return position_in_cycle < self.execute_duration

    def save_state(self):
        """Guarda el estado completo de todas las cámaras en Redis"""
        success = True
        for camera_id, vehicles in self.vehicle_registry.items():
            if not self.redis_manager.save_camera_data(camera_id, vehicles):
                success = False
        return success

    def save_camera_state(self, camera_id):
        """Guarda el estado de una cámara específica en Redis"""
        if camera_id in self.vehicle_registry:
            return self.redis_manager.save_camera_data(camera_id, self.vehicle_registry[camera_id])
        return False
    
    def load_camera_state(self, camera_id):
        """Carga el estado de una cámara específica desde Redis"""
        camera_data = self.redis_manager.load_camera_data(camera_id)
        if camera_data:
            self.vehicle_registry[camera_id] = camera_data
            return True
        return False
    
    def process(self, camera_id, object_dict):
        current_time = time.time()

        # INICIALIZACIÓN
        if not self.last_check:
            self.last_check = current_time
            logger.info(f"[INICIALIZACIÓN] Sistema inicializado para cámara {camera_id}")
            return []
        
        # CONTROL DE CICLO DE EJECUCIÓN
        elapsed_time = current_time - self.last_check
        cycle_duration = self.execute_duration + self.interval_sec
        position_in_cycle = elapsed_time % cycle_duration
        
        # ESTADO INACTIVO
        if position_in_cycle >= self.execute_duration:
            tiempo_restante = cycle_duration - position_in_cycle
            logger.info(f"[INACTIVO] Detector en pausa para cámara {camera_id} - "
                       f"Tiempo restante: {tiempo_restante:.2f}s de {self.interval_sec}s")
            
            
            # Limpiar la marca de backup para el próximo ciclo
            if hasattr(self, 'current_cycle_backed_up'):
                del self.current_cycle_backed_up

            return []
        
        # ESTADO ACTIVO
        logger.info(f"[ACTIVO] Procesando cámara {camera_id} - "
                   f"Tiempo activo: {position_in_cycle:.2f}s / {self.execute_duration}s")
        
        # Si estamos cerca del final del ciclo activo, realizar backup (si no se ha hecho en este ciclo)
        current_cycle_id = int(current_time / cycle_duration)
        if self.execute_duration - position_in_cycle <= 15:  # 15 segundos antes de finalizar
            if not hasattr(self, 'current_cycle_backed_up') or self.current_cycle_backed_up != current_cycle_id:
                # Solo guardar la cámara actual en lugar de todo el registro
                self.save_camera_state(camera_id)
                self.current_cycle_backed_up = current_cycle_id
                logger.info(f"Backup automático para cámara {camera_id} realizado al final del ciclo {current_cycle_id}")
        
        if elapsed_time >= cycle_duration:
            self.last_check = current_time - position_in_cycle
            logger.info(f"[CICLO] Completado ciclo completo de {cycle_duration}s - Reiniciando contador")

        # # ADICION RESPALDO PERIÓDICO A REDIS
        # if current_time - self.last_backup_time >= self.backup_interval:
        #     self.save_state()
        #     self.last_backup_time = current_time
        #     logger.info(f"Backup automático realizado a Redis. Próximo en {self.backup_interval/60} minutos")
        
        # PROCESAMIENTO DE VEHÍCULOS
        abandoned = []
        vehicles = self._get_all_vehicles(object_dict)
        
        if camera_id not in self.vehicle_registry:
            self.vehicle_registry[camera_id] = dict()
            logger.info(f"Inicializando registro para cámara {camera_id}")
        
        # Limpiar informes antiguos
        self._clean_old_reports(camera_id, current_time)
        
        # Lista de IDs detectados en este frame para control de limpieza
        current_detected_ids = set()
        
        # Procesar cada vehículo detectado
        for vehicle in vehicles:
            current_id = vehicle[DATA_TRAKING_ID]
            current_coords = vehicle[DATA_OBJETO_COORDENADAS]
            current_centroid = self._calc_centroid(current_coords)
            vehicle_type = vehicle['vehicle_type']
            
            # Añadir a la lista de IDs detectados actualmente
            current_detected_ids.add(current_id)

            epoch_object = vehicle.get(DATA_OBJETO_EPOCH_OBJECT, None)
            
            # Buscar si este vehículo coincide con alguno previamente registrado
            matching_id = self._find_matching_vehicle(camera_id, current_id, current_coords, current_centroid)
            
            if matching_id and matching_id != current_id:
                # Tenemos un vehículo que cambió de ID pero es el mismo
                logger.info(f"Vehículo con ID={current_id} identificado como el mismo que ID={matching_id}, "
                           f"manteniendo seguimiento")
                
                # Actualizar el registro manteniendo el tiempo acumulado
                old_data = self.vehicle_registry[camera_id][matching_id]
                old_centroid = old_data["centroid"]
                
                # Si el vehículo se movió significativamente, reiniciar contador
                if not self._is_same_position(old_centroid, current_centroid):
                    
                    # Se movió, reiniciar tiempo de abandono pero mantener first_seen
                    self.vehicle_registry[camera_id][current_id] = {
                        "centroid": current_centroid,
                        "last_seen": current_time,
                        "first_seen": old_data["first_seen"],  # Mantener tiempo original
                        "abandoned_time": 0,  # Reiniciar tiempo de abandono
                        "coords": current_coords,
                        "type": vehicle_type,
                        "reported": False,
                        "epoch_object": epoch_object
                    }
                    # Eliminar el registro antiguo con el ID anterior
                    del self.vehicle_registry[camera_id][matching_id]
                else:
                    # Misma posición, actualizar y acumular tiempo
                    time_increment = current_time - old_data["last_seen"]
                    self.vehicle_registry[camera_id][current_id] = {
                        "centroid": current_centroid,
                        "last_seen": current_time,
                        "first_seen": old_data["first_seen"],  # Mantener tiempo original
                        "abandoned_time": old_data["abandoned_time"] + time_increment,
                        "coords": current_coords,
                        "type": vehicle_type,
                        "reported": old_data["reported"],
                        "epoch_object": epoch_object 
                    }
                    # Eliminar el registro antiguo con el ID anterior
                    del self.vehicle_registry[camera_id][matching_id]
            
            elif current_id in self.vehicle_registry[camera_id]:
                # Vehículo existente con mismo ID
                old_data = self.vehicle_registry[camera_id][current_id]
                old_centroid = old_data["centroid"]
                
                # Si el vehículo se movió significativamente, reiniciar contador
                if not self._is_same_position(old_centroid, current_centroid):
                    
                    # Se movió, reiniciar tiempo de abandono pero mantener first_seen
                    self.vehicle_registry[camera_id][current_id] = {
                        "centroid": current_centroid,
                        "last_seen": current_time,
                        "first_seen": old_data["first_seen"],  # Mantener tiempo original
                        "abandoned_time": 0,  # Reiniciar tiempo de abandono
                        "coords": current_coords,
                        "type": vehicle_type,
                        "reported": False,
                        "epoch_object": epoch_object 
                    }
                else:
                    # Misma posición, actualizar y acumular tiempo
                    time_increment = current_time - old_data["last_seen"]
                    self.vehicle_registry[camera_id][current_id] = {
                        "centroid": current_centroid,
                        "last_seen": current_time,
                        "first_seen": old_data["first_seen"],  # Mantener tiempo original
                        "abandoned_time": old_data["abandoned_time"] + time_increment,
                        "coords": current_coords,
                        "type": vehicle_type,
                        "reported": old_data["reported"],
                        "epoch_object": epoch_object 
                    }
            else:
                # Vehículo nuevo, crear registro
                self.vehicle_registry[camera_id][current_id] = {
                    "centroid": current_centroid,
                    "last_seen": current_time,
                    "first_seen": current_time,  # Tiempo de primera detección
                    "abandoned_time": 0,
                    "coords": current_coords,
                    "type": vehicle_type,
                    "reported": False,
                    "epoch_object": epoch_object 
                }
            
            # Verificar si el vehículo se considera abandonado
            vehicle_data = self.vehicle_registry[camera_id][current_id]
            
            if vehicle_data["abandoned_time"] >= self.tiempo_considerado_abandono:
                # Calcular el tiempo total desde la primera detección (para el reporte)
                total_time_detected = current_time - vehicle_data["first_seen"]

                tiempo_abandono_minutos = round(vehicle_data["abandoned_time"] / 60, 2)  # Redondear a 2 decimales
                tiempo_total_minutos = round(total_time_detected / 60, 2)  # Redondear a 2 decimales
                
                epoch_object = vehicle.get(DATA_EPOCH_FRAME, None)

                # Verificar si es un duplicado antes de reportar
                if not vehicle_data["reported"] and not self._is_duplicate_report(camera_id, current_id, 
                                                     current_centroid, current_coords, current_time):
                    abandoned.append({
                        #id_tracking agregado
                        "id_tracking": current_id,
                        "vehicle_type": vehicle_type,
                        "coords": current_coords,
                        "tiempo_abandono": tiempo_abandono_minutos ,  # Tiempo acumulado en la misma posición
                        "tiempo_total": tiempo_total_minutos,  # Tiempo total desde primera detección
                        "epoch_object": epoch_object,
                        # "tiempo_abandono": vehicle_data["abandoned_time"],  # Tiempo acumulado en la misma posición
                        # "tiempo_total": total_time_detected  # Tiempo total desde primera detección
                        "category": 1,
                        "type": 4,
                        "camera_id": camera_id,
                        "object_id": object_dict["object_id"],
                        'message'   : f"Vehiculo detectado como abandonado en cámara {camera_id}",
                    })
                    
                    # Marcar como reportado para evitar duplicados
                    self.vehicle_registry[camera_id][current_id]["reported"] = True
                    
                    # Registrar este informe como reciente para deduplicación
                    self.recent_abandoned_reports[camera_id].append(
                        (current_id, current_time, current_coords)
                    )
                    
                    logger.info(f"[ABANDONO] Vehículo {current_id} tipo {vehicle_type} abandonado: "
                               f"Tiempo en posición: {vehicle_data['abandoned_time']:.2f}min, "
                               f"Tiempo total detectado: {total_time_detected:.2f}min" 
                               f"Epoch frame: {epoch_object}")
        
        # OPCIONAL: Limpieza de vehículos que ya no se detectan
        # Esto depende de tus necesidades - podrías querer mantenerlos por más tiempo
        # """
        ids_to_remove = []
        for vehicle_id in self.vehicle_registry[camera_id]:
            if vehicle_id not in current_detected_ids:
                # Vehículo no detectado en este frame
                last_seen = self.vehicle_registry[camera_id][vehicle_id]["last_seen"]
                if current_time - last_seen > 30:  # 30 segundos de umbral para eliminar
                    ids_to_remove.append(vehicle_id)
        
        for vehicle_id in ids_to_remove:
            logger.debug(f"Eliminando vehículo {vehicle_id} que ya no se detecta")
            del self.vehicle_registry[camera_id][vehicle_id]
        # """
        
        # Al final, antes de retornar, podemos actualizar la cámara en Redis si se han detectado abandonos
        if abandoned:
            # Si detectamos vehículos abandonados, guardar inmediatamente el estado de esta cámara
            self.save_camera_state(camera_id)
            logger.info(f"Estado de cámara {camera_id} guardado tras detectar {len(abandoned)} vehículos abandonados")

        # Resumen del procesamiento
        logger.info(f"[RESUMEN] Cámara {camera_id}: Procesados {len(vehicles)} vehículos, {len(abandoned)} considerados abandonados")

        return abandoned