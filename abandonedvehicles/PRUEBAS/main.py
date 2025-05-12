import json
import time
import os
import signal
import threading
from datetime import datetime
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher
from processing import VehicleDetector

# Configurar logger
logger = configurar_logger(name='main', log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class AbandonedVehicleSystem:
    def __init__(self):
        """Inicializa el sistema de detección de vehículos abandonados"""
        self.start_time = time.time()
        self.running = True
        
        logger.info("Construyendo sistema de detección de vehículos abandonados...")
        
        # Inicializar el publisher para enviar alertas
        self.publisher = ExamplePublisher(AMQP_URL, exchange=EXCHANGE_OUT)
        
        # Inicializar el detector con la configuración
        self.detector = VehicleDetector(
            INTERVAL_MINUTES,  
            DISTANCE_THRESHOLD,
            PROCESSING_TIME_MINUTES,
            SLEEP_TIME_MINUTES
        )
        
        # Configurar el manejo de señales para una terminación limpia
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Configurar un temporizador para publicar estadísticas periódicamente
        self._setup_stats_timer()
    
    def _signal_handler(self, sig, frame):
        """Maneja señales para terminar limpiamente"""
        logger.info(f"Señal recibida ({sig}), terminando sistema...")
        self.running = False
        
    def _setup_stats_timer(self):
        """Configura el temporizador para publicar estadísticas"""
        if not self.running:
            return
            
        # Crear y programar el temporizador
        self.stats_timer = threading.Timer(STATS_INTERVAL_SEC, self._publish_stats)
        self.stats_timer.daemon = True  # Para que termine junto con el programa principal
        self.stats_timer.start()
        
        logger.debug(f"Temporizador configurado, próximas estadísticas en {STATS_INTERVAL_SEC//60} minutos")
        
    def _publish_stats(self):
        """Publica estadísticas del sistema"""
        try:
            # Calcular tiempo de ejecución
            uptime = time.time() - self.start_time
            
            # Preparar estadísticas
            stats = {
                "timestamp": int(time.time()),
                "message_type": "system_stats",
                "system_uptime": int(uptime),
                "uptime_formatted": self._format_time_duration(uptime),
                "processing_status": "activo" if self.detector.is_processing else "reposo",
                "total_cameras": len(self.detector.vehicle_registry),
                "total_vehicles_tracked": sum(len(cam_data) for cam_data in self.detector.vehicle_registry.values()),
                "total_abandoned_reported": len(self.detector.reported_vehicles),
                "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Publicar estadísticas
            self.publisher.publish_async(stats)
            logger.info(f"Estadísticas del sistema publicadas: {stats}")
            
        except Exception as e:
            logger.error(f"Error publicando estadísticas: {str(e)}")
        finally:
            # Configurar el próximo temporizador si el sistema sigue en ejecución
            self._setup_stats_timer()
    
    def _format_time_duration(self, seconds):
        """Formatea una duración en segundos a formato legible"""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
            
        return " ".join(parts)
            
    def handle_message(self, ch, method, properties, body):
        """
        Callback para procesar mensajes recibidos de RabbitMQ
        
        Args:
            ch: Canal de RabbitMQ
            method: Método de RabbitMQ
            properties: Propiedades del mensaje
            body: Contenido del mensaje
        """
        try:
            # Convertir el mensaje a diccionario
            data = json.loads(body)
            
            # Extraer datos relevantes
            camera_id = data.get(DATA_CAMERA)
            object_dict = data.get(DATA_OBJETOS_DICT, {})
            
            if not camera_id or not object_dict:
                logger.warning("Mensaje recibido sin cámara ID o diccionario de objetos")
                return
                
            # Procesar con el detector
            result = self.detector.process(camera_id, object_dict)
            
            # Si hay resultado (reporte o alerta), publicarlo
            if result:
                self.publisher.publish_async(result)
                logger.info(f"Datos publicados: {len(result.get('abandoned_vehicles', []))} vehículos abandonados en cámara {camera_id}")
                
            # Acusar recibo del mensaje
            ch.basic_ack(delivery_tag=method.delivery_tag)
                
        except json.JSONDecodeError:
            logger.error("Error decodificando mensaje JSON")
            # Acusar recibo para no procesar mensajes malformados nuevamente
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}", exc_info=True)
            # En caso de error, intentamos acusar recibo para evitar procesamiento repetido
            try:
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except:
                pass

    def run(self):
        """Inicia el sistema y el consumer de RabbitMQ"""
        try:
            logger.info("===== INICIANDO SISTEMA DE DETECCIÓN DE VEHÍCULOS ABANDONADOS =====")
            logger.info(f"PID: {os.getpid()} - Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Configuración:")
            logger.info(f"- Intervalo de detección: {self.detector.interval_sec//60} minutos")
            logger.info(f"- Umbral de distancia: {self.detector.distance_threshold} píxeles")
            logger.info(f"- Tiempo de procesamiento: {self.detector.processing_time//60} minutos")
            logger.info(f"- Tiempo de reposo: {self.detector.sleep_time//60} minutos")
            logger.info(f"- Intervalo de estadísticas: {STATS_INTERVAL_SEC//60} minutos")
            
            # Iniciar consumer en un hilo separado
            consumer = ReconnectingExampleConsumer(
                AMQP_URL,
                queue=QUEUE_IN,
                exchange=EXCHANGE_IN,
                message_callback=self.handle_message
            )
            
            # Iniciar consumer
            consumer_thread = threading.Thread(target=consumer.run)
            consumer_thread.daemon = True
            consumer_thread.start()
            
            logger.info("Sistema iniciado y esperando mensajes...")
            
            # Mantener el programa principal en ejecución
            while self.running:
                time.sleep(1)
                
            logger.info("Cerrando sistema ordenadamente...")
                
        except Exception as e:
            logger.critical(f"Error crítico en el sistema: {str(e)}", exc_info=True)
            self.running = False
            
        finally:
            # Cancelar temporizador si existe
            if hasattr(self, 'stats_timer') and self.stats_timer:
                self.stats_timer.cancel()
                
            logger.info("Sistema finalizado")

if __name__ == "__main__":
    system = AbandonedVehicleSystem()
    system.run()