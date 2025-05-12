import json
import time
import os
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher
from processing import StolenVehicleDetector
import signal
import sys
import threading


logger = configurar_logger(name="main", log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class StolenVehicleSystem:
    def __init__(self):
        """
        Inicializa el sistema de Comparador de Listas.
        """
        logger.info("Construyendo sistema de comparador de listas...")
        self.publisher = ExamplePublisher(AMQP_URL)
        self.publisher.start()
        self.detector = StolenVehicleDetector()
        self.consumer = None
        self._shutdown_flag = threading.Event()
        logger.info("Sistema inicializado correctamente")

    def handle_message(self, ch, method, properties, body):
        """
        Maneja los mensajes recibidos de RabbitMQ.
        
        Args:
            ch: Canal AMQP
            method: Método AMQP
            properties: Propiedades AMQP
            body: Contenido del mensaje
        """
        try:
            # Decodificar el mensaje JSON
            data = json.loads(body)
            
            # Extraer información relevante
            camera_id = data.get(DATA_CAMERA)
            object_dict = data.get(DATA_OBJETOS_DICT, {})
            
            # Contar el número total de objetos en todas las categorías
            total_objects = 0
            for category, objects_list in object_dict.items():
                total_objects += len(objects_list)
            
            logger.info(f"Mensaje recibido de la cámara {camera_id}")
            logger.debug(f"Objetos detectados: {total_objects}")
            
            # Procesar los datos para detectar vehículos monitoreados
            alerts = self.detector.process(camera_id, data)
            
            # Si se detectaron vehículos en alguna lista, publicar alertas
            if alerts:
                logger.warning(f"¡Se detectaron {len(alerts)} vehículos monitoreados en la cámara {camera_id}!")
                
                for alert in alerts:
                    # Obtener el tipo de lista y su nombre para mostrar
                    list_type = alert.get('list_type', 'desconocida')
                    list_display = list_type.replace('_', ' ')
                    
                    # Publicar la alerta (no se necesita modificar, ya viene completa de processing.py)
                    logger.info(f"Publicando alerta para placa: {alert.get('plate_text', 'N/A')} (lista: {list_display})")
                    self.publisher.publish_async(alert)
                    logger.info(f"Alerta de vehículo de lista '{list_display}' publicada")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error al decodificar mensaje JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}")


    def _signal_handler(self, sig, frame):
        """
        Maneja señales para cierre controlado del sistema.
        """
        logger.info(f"Señal recibida: {sig}. Iniciando cierre controlado...")
        
        # Indicar a todos los componentes que deben detenerse
        self._shutdown_flag.set()
        
        # Detener el consumer en un hilo separado para evitar deadlocks
        def stop_consumer():
            if hasattr(self, 'consumer') and self.consumer and hasattr(self.consumer, '_consumer'):
                try:
                    self.consumer._consumer.should_reconnect = False
                    self.consumer._consumer.stop()
                except Exception as e:
                    logger.error(f"Error al detener el consumer: {str(e)}")
        
        # Iniciar el proceso de cierre en un hilo separado
        shutdown_thread = threading.Thread(target=stop_consumer)
        shutdown_thread.daemon = True
        shutdown_thread.start()
        
        # Esperar un tiempo para que el consumer se detenga (con timeout)
        shutdown_thread.join(timeout=5.0)
        
        # Detener el publisher
        if hasattr(self, 'publisher') and self.publisher:
            try:
                self.publisher.stop()
            except Exception as e:
                logger.error(f"Error al detener el publisher: {str(e)}")
        
        logger.info("Sistema detenido correctamente.")
        
        # Salir de manera controlada
        sys.exit(0)

    def run(self):
        """
        Ejecuta el sistema de detección continua.
        """
        try:
            logger.info("Iniciando sistema de detección de comparador de listas")
            logger.info(f"Iniciando sistema (PID: {os.getpid()}) - Hora: {time.ctime()}")
            
            # Configurar manejo de señales para cierre controlado
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # Verificar si la conexión a Redis funciona correctamente
            try:
                self.detector.redis_client.ping()
                logger.info("Conexión a Redis establecida correctamente")
                
                # Comprobar que hay datos de vehículos monitoreados
                total_count = 0
                list_counts = {}
                sample_plates = []

                # Verificar si están definidos los tipos de lista
                if hasattr(self.detector, 'list_types') and self.detector.list_types:
                    # Contar vehículos por tipo de lista
                    for list_type in self.detector.list_types:
                        # Obtener placas en este tipo de lista
                        list_pattern = f"{list_type}:*"
                        cursor = 0
                        count = 0
                        plate_samples = []
                        
                        # Escanear el hash principal para encontrar placas de este tipo
                        while True:
                            cursor, keys = self.detector.redis_client.hscan(
                                self.detector.main_hash, cursor, match=list_pattern, count=100
                            )
                            decoded_keys = [k.decode('utf-8') for k in keys]
                            count += len(decoded_keys)
                            
                            # Guardar hasta 3 ejemplos de cada lista
                            if len(plate_samples) < 3 and decoded_keys:
                                for key in decoded_keys[:3]:
                                    plate = key.split(':', 1)[1]  # Extraer la placa de "tipo:placa"
                                    plate_samples.append(f"{plate} ({list_type})")
                                    
                            if cursor == 0:
                                break
                                
                        list_counts[list_type] = count
                        total_count += count
                        sample_plates.extend(plate_samples[:3])  # Tomar máximo 3 por lista
                        
                    logger.info(f"Encontrados {total_count} vehículos monitoreados en {len(list_counts)} listas")
                    
                    # Mostrar desglose por lista
                    for list_type, count in list_counts.items():
                        if count > 0:
                            logger.info(f"- Lista '{list_type}': {count} vehículos")
                            
                    # Mostrar algunos ejemplos
                    if sample_plates:
                        logger.info(f"Ejemplos de placas: {', '.join(sample_plates[:5])}")  # Mostrar máximo 5 en total
                else:
                    logger.warning("No se han encontrado listas de vehículos configuradas")
            except Exception as e:
                logger.warning(f"No se pudo verificar la conexión a Redis: {str(e)}")

            # Iniciar el consumidor para recibir mensajes continuamente
            self.consumer = ReconnectingExampleConsumer(
                AMQP_URL,
                message_callback=self.handle_message,
                exchange=EXCHANGE_IN,
                queue=QUEUE_IN,
                prefetch_count=50,         # Valor recomendado para alta carga
                worker_threads=4           # Ajustar según núcleos disponibles
            )
            
            logger.info(f"Escuchando mensajes del exchange {EXCHANGE_IN} en la cola {QUEUE_IN}")
            self.consumer.run()
            
        except KeyboardInterrupt:
            # Manejar Ctrl+C explícitamente aquí
            self._signal_handler(signal.SIGINT, None)
        except Exception as e:
            logger.critical(f"Error crítico en el sistema: {str(e)}", exc_info=True)
            # Intentar cerrar recursos antes de salir
            try:
                self._signal_handler(signal.SIGTERM, None)
            except:
                pass
            raise

if __name__ == "__main__":
    system = StolenVehicleSystem()
    system.run()