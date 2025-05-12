import json
import time
import logging
import math
import schedule
import threading
from datetime import datetime
from collections import defaultdict

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("abandoned_vehicles.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AbandonedVehicleDetector")

class AbandonedVehicleDetector:
    def __init__(self, snapshot_interval=900, check_interval=3600, distance_threshold=20, time_threshold=10800000):
        """
        Inicializar el detector de vehículos abandonados optimizado para procesamiento periódico
        
        Args:
            snapshot_interval (int): Intervalo entre capturas de snapshots en segundos (por defecto 15 minutos)
            check_interval (int): Intervalo para verificación completa en segundos (por defecto 1 hora)
            distance_threshold (int): Umbral de distancia para considerar que un vehículo está en la misma posición
            time_threshold (int): Tiempo en milisegundos para considerar un vehículo como abandonado (por defecto 3 horas)
        """
        self.snapshot_interval = snapshot_interval  # Intervalo entre snapshots en segundos
        self.check_interval = check_interval  # Intervalo de verificación completa en segundos
        self.distance_threshold = distance_threshold  # Umbral de distancia
        self.time_threshold = time_threshold  # Tiempo para considerar vehículo abandonado en milisegundos
        
        # Estructura para almacenar snapshots de vehículos detectados por cámara
        # {camera_id: {timestamp: {object_id: {'coords': [x1, y1, x2, y2], 'centroid': (x, y)}}}}
        self.snapshots = defaultdict(dict)
        
        # Estructura para seguimiento de vehículos estacionarios
        # {camera_id: {object_id: {'coords': [x1, y1, x2, y2], 'centroid': (x, y), 'snapshots_count': n, 'first_seen': timestamp, 'last_seen': timestamp}}}
        self.stationary_vehicles = defaultdict(dict)
        
        # Lista de vehículos marcados como abandonados
        # {camera_id: {object_id: {'coords': [x1, y1, x2, y2], 'centroid': (x, y), 'time_stationary': seconds, 'snapshots_count': n}}}
        self.abandoned_vehicles = defaultdict(dict)
        
        # Cola para almacenar datos de frames entrantes que serán procesados solo en los snapshots
        self.incoming_data_queue = []
        
        # Flag para indicar si es momento de tomar un snapshot
        self.take_snapshot_flag = False
        
        # Timestamp del último snapshot tomado
        self.last_snapshot_time = 0
        
        # Configurar el planificador de tareas
        self._setup_scheduler()
        
    def _setup_scheduler(self):
        """Configura las tareas programadas"""
        # Programar la captura de snapshots
        schedule.every(self.snapshot_interval).seconds.do(self._set_snapshot_flag)
        
        # Programar la verificación de vehículos abandonados
        schedule.every(self.check_interval).seconds.do(self.check_abandoned_vehicles)
        
        # Iniciar un hilo para ejecutar el planificador
        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()
        
    def _run_scheduler(self):
        """Ejecuta el planificador de tareas en segundo plano"""
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    def _set_snapshot_flag(self):
        """Establece el flag para tomar un snapshot en la próxima oportunidad"""
        self.take_snapshot_flag = True
        logger.info("Programado próximo snapshot para procesar")
        return schedule.CancelJob  # Cancela este trabajo para evitar acumulación si hay retrasos
        
    def process_incoming_data(self, frame_data):
        """
        Recibe datos de un frame y los encola para su procesamiento futuro.
        Este método debería ser llamado cuando se reciben datos en tiempo real.
        """
        try:
            if isinstance(frame_data, str):
                data = json.loads(frame_data)
            else:
                data = frame_data
                
            # Simplemente almacenamos los datos recibidos en la cola
            self.incoming_data_queue.append(data)
            
            # Si es tiempo de tomar un snapshot y tenemos datos, procesamos el último frame recibido
            if self.take_snapshot_flag and self.incoming_data_queue:
                self.take_snapshot()
                
            # Mantener la cola en un tamaño razonable
            if len(self.incoming_data_queue) > 100:  # Límite arbitrario para evitar consumo excesivo de memoria
                self.incoming_data_queue = self.incoming_data_queue[-50:]  # Conservar solo los 50 más recientes
                
        except Exception as e:
            logger.error(f"Error al procesar datos entrantes: {str(e)}")
    
    def take_snapshot(self):
        """
        Toma un snapshot de la situación actual utilizando el último frame disponible
        """
        if not self.incoming_data_queue:
            logger.warning("No hay datos disponibles para tomar snapshot")
            self.take_snapshot_flag = False
            return
        
        # Tomamos el último frame recibido
        data = self.incoming_data_queue[-1]
        self.incoming_data_queue = []  # Limpiamos la cola después de tomar el snapshot
        
        try:
            camera_id = data.get("camera_id")
            epoch_frame = data.get("epoch_frame")
            object_dict = data.get("object_dict", {})
            
            # Registro del snapshot
            timestamp = int(time.time() * 1000)
            self.snapshots[camera_id][timestamp] = {}
            
            logger.info(f"Tomando snapshot para cámara {camera_id} a las {datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Procesar objetos detectados en este snapshot
            for object_type, objects in object_dict.items():
                for obj in objects:
                    coords = obj.get("coords")
                    object_id = obj.get("object_id")
                    accuracy = obj.get("accuracy")
                    
                    if not coords or not object_id:
                        continue
                    
                    # Calcular el centro del objeto
                    centroid = self._calculate_centroid(coords)
                    
                    # Registrar este objeto en el snapshot actual
                    self.snapshots[camera_id][timestamp][object_id] = {
                        'coords': coords,
                        'centroid': centroid,
                        'accuracy': accuracy
                    }
                    
                    # Verificar si este objeto coincide con alguno previamente detectado
                    self._match_vehicle_with_previous_snapshots(camera_id, object_id, coords, centroid, timestamp, accuracy)
            
            # Limpiar snapshots antiguos (mantener solo los últimos que correspondan al umbral de tiempo)
            self._clean_old_snapshots(camera_id)
            
        except Exception as e:
            logger.error(f"Error al tomar snapshot: {str(e)}")
        
        # Restablecer el flag
        self.take_snapshot_flag = False
        self.last_snapshot_time = int(time.time())
    
    def _calculate_centroid(self, coords):
        """Calcula el centro de un objeto basado en sus coordenadas [x1, y1, x2, y2]"""
        x1, y1, x2, y2 = coords
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    
    def _calculate_distance(self, centroid1, centroid2):
        """Calcula la distancia euclidiana entre dos centroides"""
        return math.sqrt((centroid1[0] - centroid2[0])**2 + (centroid1[1] - centroid2[1])**2)
    
    def _match_vehicle_with_previous_snapshots(self, camera_id, object_id, coords, centroid, timestamp, accuracy):
        """
        Verifica si el vehículo actual coincide con alguno previamente detectado en snapshots anteriores
        """
        # Verificar si este vehículo ya está siendo rastreado como estacionario
        if object_id in self.stationary_vehicles[camera_id]:
            vehicle = self.stationary_vehicles[camera_id][object_id]
            old_centroid = vehicle['centroid']
            
            # Calcular la distancia entre la posición anterior y la actual
            distance = self._calculate_distance(old_centroid, centroid)
            
            # Si el vehículo se ha movido más que el umbral, actualizar su posición
            if distance > self.distance_threshold:
                # El vehículo se ha movido, reiniciar su seguimiento
                vehicle['coords'] = coords
                vehicle['centroid'] = centroid
                vehicle['first_seen'] = timestamp
                vehicle['last_seen'] = timestamp
                vehicle['snapshots_count'] = 1
                
                # Si estaba marcado como abandonado, removerlo
                if object_id in self.abandoned_vehicles[camera_id]:
                    del self.abandoned_vehicles[camera_id][object_id]
                    logger.info(f"Vehículo {object_id} de cámara {camera_id} se ha movido y ya no está abandonado")
            else:
                # El vehículo sigue en la misma posición
                vehicle['last_seen'] = timestamp
                vehicle['snapshots_count'] += 1
                
                # Verificar si ha sido detectado en suficientes snapshots para considerarlo abandonado
                snapshots_required = max(3, int(self.time_threshold / (self.snapshot_interval * 1000)))
                time_stationary = timestamp - vehicle['first_seen']
                
                if (vehicle['snapshots_count'] >= snapshots_required and 
                    time_stationary >= self.time_threshold and 
                    object_id not in self.abandoned_vehicles[camera_id]):
                    
                    self.abandoned_vehicles[camera_id][object_id] = {
                        'coords': coords,
                        'centroid': centroid,
                        'time_stationary': time_stationary,
                        'snapshots_count': vehicle['snapshots_count'],
                        'first_seen': vehicle['first_seen'],
                        'last_seen': timestamp,
                        'accuracy': accuracy
                    }
                    logger.warning(f"¡Vehículo abandonado detectado! ID: {object_id}, Cámara: {camera_id}, "
                                  f"Tiempo: {time_stationary/1000:.2f} segundos, "
                                  f"Detectado en {vehicle['snapshots_count']} snapshots consecutivos")
        else:
            # Nuevo vehículo para seguimiento
            # Primero verificamos si existe un vehículo similar en la misma área (podría ser el mismo con ID diferente)
            matched = False
            
            for existing_id, existing_vehicle in list(self.stationary_vehicles[camera_id].items()):
                distance = self._calculate_distance(existing_vehicle['centroid'], centroid)
                if distance <= self.distance_threshold:
                    # Probablemente es el mismo vehículo con un ID diferente,
                    # actualizamos el registro existente y no creamos uno nuevo
                    existing_vehicle['last_seen'] = timestamp
                    existing_vehicle['snapshots_count'] += 1
                    matched = True
                    break
            
            if not matched:
                # Registrar nuevo vehículo
                self.stationary_vehicles[camera_id][object_id] = {
                    'coords': coords,
                    'centroid': centroid,
                    'first_seen': timestamp,
                    'last_seen': timestamp,
                    'snapshots_count': 1,
                    'accuracy': accuracy
                }
                logger.debug(f"Nuevo vehículo registrado: ID {object_id} en cámara {camera_id}")
    
    def _clean_old_snapshots(self, camera_id):
        """Limpia los snapshots antiguos para conservar memoria"""
        current_time = int(time.time() * 1000)
        retention_period = self.time_threshold * 2  # Conservamos snapshots por el doble del umbral de abandono
        
        if camera_id in self.snapshots:
            timestamps_to_remove = []
            
            for timestamp in self.snapshots[camera_id]:
                if current_time - timestamp > retention_period:
                    timestamps_to_remove.append(timestamp)
            
            for timestamp in timestamps_to_remove:
                del self.snapshots[camera_id][timestamp]
            
            if timestamps_to_remove:
                logger.debug(f"Se eliminaron {len(timestamps_to_remove)} snapshots antiguos de la cámara {camera_id}")
    
    def check_abandoned_vehicles(self):
        """Verifica los vehículos abandonados y actualiza la lista"""
        current_time = int(time.time() * 1000)
        abandoned_count = 0
        
        for camera_id, vehicles in self.stationary_vehicles.items():
            for object_id, vehicle in list(vehicles.items()):
                # Si el vehículo no ha sido visto en varios snapshots consecutivos, consideramos que ya no está
                consecutive_missed_snapshots = (current_time - vehicle['last_seen']) / (self.snapshot_interval * 1000)
                
                if consecutive_missed_snapshots > 2:  # Si ha faltado en más de 2 snapshots consecutivos
                    logger.info(f"Eliminando vehículo {object_id} de cámara {camera_id} porque no ha sido detectado en los últimos snapshots")
                    del vehicles[object_id]
                    
                    # Si estaba marcado como abandonado, también lo eliminamos
                    if object_id in self.abandoned_vehicles.get(camera_id, {}):
                        del self.abandoned_vehicles[camera_id][object_id]
                
                # Verificar si ha estado estacionario por suficiente tiempo para considerarlo abandonado
                elif (current_time - vehicle['first_seen'] >= self.time_threshold and 
                      vehicle['snapshots_count'] >= max(3, int(self.time_threshold / (self.snapshot_interval * 1000)))):
                    
                    if object_id not in self.abandoned_vehicles[camera_id]:
                        self.abandoned_vehicles[camera_id][object_id] = {
                            'coords': vehicle['coords'],
                            'centroid': vehicle['centroid'],
                            'time_stationary': current_time - vehicle['first_seen'],
                            'snapshots_count': vehicle['snapshots_count'],
                            'first_seen': vehicle['first_seen'],
                            'last_seen': vehicle['last_seen'],
                            'accuracy': vehicle.get('accuracy', 0)
                        }
                        abandoned_count += 1
                        logger.warning(f"¡Vehículo abandonado detectado! ID: {object_id}, Cámara: {camera_id}, "
                                     f"Tiempo: {(current_time - vehicle['first_seen'])/1000:.2f} segundos, "
                                     f"Detectado en {vehicle['snapshots_count']} snapshots")
        
        # Generar y publicar informe solo si hay vehículos abandonados
        if abandoned_count > 0 or self.abandoned_vehicles:
            report = self.generate_abandoned_vehicles_report()
            self.publish_report(report)
            logger.info(f"Se detectaron {abandoned_count} nuevos vehículos abandonados, {len(self.abandoned_vehicles)} en total")
        else:
            logger.info("No se detectaron vehículos abandonados")
            
        return abandoned_count
    
    def generate_abandoned_vehicles_report(self):
        """Genera un informe de vehículos abandonados para publicar en el exchange"""
        report = {
            "timestamp": int(time.time() * 1000),
            "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "abandoned_vehicles": {}
        }
        
        for camera_id, vehicles in self.abandoned_vehicles.items():
            report["abandoned_vehicles"][camera_id] = []
            for object_id, vehicle in vehicles.items():
                report["abandoned_vehicles"][camera_id].append({
                    "object_id": object_id,
                    "coords": vehicle["coords"],
                    "centroid": vehicle["centroid"],
                    "time_stationary": vehicle["time_stationary"],
                    "first_seen": vehicle["first_seen"],
                    "last_seen": vehicle["last_seen"],
                    "snapshots_detected": vehicle["snapshots_count"],
                    "hours_abandoned": round(vehicle["time_stationary"] / (3600 * 1000), 2),
                    "accuracy": vehicle.get("accuracy", 0)
                })
        
        return report
    
    def publish_report(self, report):
        """
        Publica el informe en un nuevo exchange 
        (Esta función debería ser implementada según el sistema de mensajería específico)
        """
        # Ejemplo de publicación (simulado)
        logger.info(f"Publicando reporte de vehículos abandonados: {json.dumps(report, indent=2)}")
        
        # Aquí iría la lógica real para publicar en el exchange
        # Por ejemplo: rabbitmq_channel.basic_publish(exchange='abandoned_vehicles', routing_key='', body=json.dumps(report))
        
        return True
    
    def run(self):
        """Ejecuta el detector de vehículos abandonados en un bucle continuo"""
        logger.info(f"Iniciando sistema de detección de vehículos abandonados")
        logger.info(f"Intervalo de snapshots: {self.snapshot_interval} segundos")
        logger.info(f"Intervalo de verificación completa: {self.check_interval} segundos")
        logger.info(f"Umbral de tiempo para considerar abandono: {self.time_threshold/1000/60} minutos")
        
        try:
            # Este bucle se encarga de tomar snapshots periódicamente y verificar vehículos abandonados
            # El planificador en segundo plano se encargará de activar las banderas correspondientes
            while True:
                time.sleep(1)  # Solo para evitar consumo excesivo de CPU
                
        except KeyboardInterrupt:
            logger.info("Sistema de detección detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el sistema de detección: {str(e)}")
            raise
            

# Función para simular la recepción de datos
def simulate_data_stream(detector, interval_seconds=1, duration_minutes=10):
    """
    Simula una transmisión de datos de la cámara
    
    Args:
        detector: Instancia del detector
        interval_seconds: Intervalo entre frames en segundos
        duration_minutes: Duración total de la simulación en minutos
    """
    # Base para la simulación
    base_data = {
        "camera_id": "4", 
        "status_frame": True, 
        "zone_restricted": {"parking": {"coords": [[0.4375, 0.9229], [0.4344, 0], [0.675, 0], [0.9688, 0.8896]], "minimum_time": 60000}}, 
        "candidate_frame": True, 
        "shape": [1080, 1920, 3]
    }
    
    # Lista de vehículos para simular
    vehicles = [
        # Vehículo estacionario (no se moverá)
        {
            "object_id": "vehicle_001",
            "base_coords": [100, 100, 200, 180],
            "movement": 0  # No se mueve
        },
        # Vehículo que se mueve ligeramente (vibración)
        {
            "object_id": "vehicle_002",
            "base_coords": [300, 200, 400, 280],
            "movement": 5  # Se mueve ligeramente
        },
        # Vehículo que se mueve significativamente
        {
            "object_id": "vehicle_003",
            "base_coords": [500, 300, 600, 380],
            "movement": 30  # Se mueve bastante
        },
        # Vehículo que aparece y desaparece
        {
            "object_id": "vehicle_004",
            "base_coords": [700, 400, 800, 480],
            "movement": 0,
            "intermittent": True
        }
    ]
    
    start_time = time.time()
    frame_count = 0
    end_time = start_time + (duration_minutes * 60)
    
    logger.info(f"Iniciando simulación de transmisión de datos por {duration_minutes} minutos")
    
    while time.time() < end_time:
        # Generar datos para este frame
        current_time = int(time.time() * 1000)
        frame_data = base_data.copy()
        frame_data["epoch_frame"] = current_time
        frame_data["init_time_frame"] = current_time + 10
        frame_data["final_time_frame"] = current_time + 20
        
        # Generar objetos detectados
        frame_objects = []
        for vehicle in vehicles:
            # Para vehículos intermitentes, aparecen y desaparecen
            if vehicle.get("intermittent", False) and frame_count % 10 < 5:
                continue
                
            # Calcular coordenadas con "movimiento"
            base_coords = vehicle["base_coords"]
            if vehicle["movement"] > 0:
                # Simulación simple de movimiento con un patrón sinusoidal
                offset_x = int(vehicle["movement"] * math.sin(frame_count / 10))
                offset_y = int(vehicle["movement"] * math.cos(frame_count / 10))
            else:
                offset_x, offset_y = 0, 0
                
            coords = [
                base_coords[0] + offset_x,
                base_coords[1] + offset_y,
                base_coords[2] + offset_x,
                base_coords[3] + offset_y
            ]
            
            # Crear objeto detectado
            obj = {
                "coords": coords,
                "accuracy": 75 + (frame_count % 20),  # Variación en precisión
                "epoch_object": current_time,
                "id_tracking": int(str(current_time) + str(current_time)[-4:]),
                "candidate": False,
                "status_object": True,
                "atributtes_list": [1, 2],
                "object_id": vehicle["object_id"]
            }
            frame_objects.append(obj)
        
        # Añadir objetos al frame
        frame_data["n_objects"] = len(frame_objects)
        frame_data["object_dict"] = {"3": frame_objects}
        
        # Enviar datos al detector
        detector.process_incoming_data(frame_data)
        
        # Incrementar contador y esperar
        frame_count += 1
        time.sleep(interval_seconds)
    
    logger.info(f"Simulación finalizada. Se enviaron {frame_count} frames.")

# Ejemplo de uso del sistema
if __name__ == "__main__":
    # Configuración del detector optimizado
    detector = AbandonedVehicleDetector(
        snapshot_interval=300,  # 5 minutos en segundos (intervalo entre snapshots)
        check_interval=3600,    # 1 hora en segundos (intervalo para verificación completa)
        distance_threshold=20,  # Umbral de distancia para considerar que un vehículo está en la misma posición
        time_threshold=3*3600*1000  # 3 horas en milisegundos para considerar un vehículo como abandonado
    )
    
    # Iniciar simulación en un hilo separado
    sim_thread = threading.Thread(
        target=simulate_data_stream,
        args=(detector, 1, 60),  # 1 segundo entre frames, 60 minutos de duración
        daemon=True
    )
    sim_thread.start()
    
    # Iniciar el detector
    detector.run()