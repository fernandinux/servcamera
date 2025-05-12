import json
import time
import sys
import signal
import os
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher
from processing import VehicleDetector

logger = configurar_logger(name='main', log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 

class AbandonedVehicleSystem:
    def __init__(self):
        self.start_time = time.time()
        logger.info("Construyendo sistema...")
        self.publisher = ExamplePublisher(AMQP_URL)
        self.publisher.start()
        self.detector = VehicleDetector(
            interval_minutes=300, # tiempo entre ciclos de detección
            execute_duration=5,   # duración de cada ciclo
            distance_threshold=30, # umbral de distancia para considerar mismo vehículo
            tiempo_considerado_abandono=DEFAULT_ABANDONO_HORAS  # valor predeterminado desde config.py
        )
        
        # Configurar manejadores de señales para guardado al salir
        self.setup_signal_handlers()
        
    def setup_signal_handlers(self):
        """Configura manejadores de señales para guardar estado antes de cerrar"""
        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)
        logger.info("Manejadores de señales configurados")
        
    def handle_exit(self, signum, frame):
        """Maneja la salida del programa guardando el estado"""
        logger.info(f"Señal {signum} recibida, guardando estado antes de salir...")
        if hasattr(self, 'detector'):
            # Guardar el estado de todas las cámaras
            self.detector.save_state()
        logger.info("Estado guardado. Terminando...")
        sys.exit(0)
        
    def handle_message(self, ch, method, properties, body):
        try:
            data = json.loads(body)
            camera_id = data.get(DATA_CAMERA)
            object_dict = data.get(DATA_OBJETOS_DICT, {})
            
            # Extraer el tiempo_considerado_abandono del mensaje si existe
            tiempo_abandono = data.get("tiempo_considerado_abandono", None)
            
            # Actualizar el valor en el detector si viene en el mensaje
            if tiempo_abandono is not None:
                try:
                    tiempo_abandono = float(tiempo_abandono)
                    if tiempo_abandono > 0:
                        # Actualizar el valor en el detector (convertir horas a segundos)
                        self.detector.tiempo_considerado_abandono = tiempo_abandono * 3600
                        logger.info(f"Tiempo de abandono actualizado a {tiempo_abandono} horas")
                except (ValueError, TypeError):
                    logger.warning(f"Valor de tiempo_considerado_abandono inválido: {tiempo_abandono}. Usando valor por defecto.")

            logger.info(f"Procesando mensaje para cámara {camera_id}")
            
            # Verificar si tenemos los datos más recientes de esta cámara desde Redis
            if not hasattr(self, 'last_camera_load') or self.last_camera_load.get(camera_id, 0) < time.time() - 3600:
                # No se ha cargado esta cámara en la última hora, intentar cargar desde Redis
                logger.info(f"Cargando datos actualizados de cámara {camera_id} desde Redis")
                self.detector.load_camera_state(camera_id)
                
                # Actualizar registro de última carga
                if not hasattr(self, 'last_camera_load'):
                    self.last_camera_load = {}
                self.last_camera_load[camera_id] = time.time()
            
            # Procesar mensaje con el detector
            abandoned_vehicles = self.detector.process(camera_id, object_dict)
            
            if abandoned_vehicles:
                for vehicle in abandoned_vehicles:
                    logger.info(f"Detalles del vehículo abandonado: ID={vehicle['id_tracking']}, "
                                f"Tipo={vehicle['vehicle_type']}, "
                                f"Tiempo abandonado={vehicle.get('tiempo_abandono', 'N/A')} min, "
                                f"Epoch object={vehicle.get('epoch_object', 'N/A')}")

                    alert = vehicle
                    self.publisher.publish_async(alert)
                
                logger.info(f'Vehículos detectados: {len(abandoned_vehicles)}')
                logger.info(f"Datos publicados")
                
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}")

    def run(self):
        logger.info("Iniciando sistema de detección de vehículos abandonados")

        logger.info(f"Iniciando sistema (PID: {os.getpid()}) - Hora: {time.ctime()}")
        logger.info(f"Configuración - Intervalo: {self.detector.interval_sec//60} min, "
                   f"Umbral: {self.detector.distance_threshold} px, "
                   f"Tiempo para considerar abandono: {self.detector.tiempo_considerado_abandono/3600} horas")
        
        consumer = ReconnectingExampleConsumer(
            AMQP_URL,
            message_callback=self.handle_message    
        )
        consumer.run()

if __name__ == "__main__":
    system = AbandonedVehicleSystem()
    system.run()