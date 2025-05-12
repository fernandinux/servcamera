import threading
import json
import time
import logging
from config import *
from config_logger import configurar_logger
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher
from processing import procesamiento_coordenadas_sync

logger = configurar_logger(name='main', log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None 

def publish_combined_callback(output_data):
    if publisher:
        publisher.publish_async(
            output_data,
            exchange='objs_zones',  # Exchange salida
            routing_key=''  # Fanout no usa routing key
        )
        logger.info(f"Datos publicados para cámara {output_data['camera_id']}")
    else:
        logger.error("Publisher no inicializado")


def rabbitmq_message_callback(ch, method, properties, body):
    """
    Callback para procesar mensajes recibidos de RabbitMQ
    """
    try:
        data = json.loads(body)
        thread = threading.Thread(
            target=procesamiento_coordenadas_sync, 
            args=(data, publish_combined_callback)
        )

        thread.start() 

    except Exception as e:
        logger.error(f"Error en rabbitmq_message_callback: {str(e)}")


def main():

    global publisher
    logger.info("Starting publisher...")
    publisher = ExamplePublisher(AMQP_URL)
    publisher.start()

    logger.info("Starting consumer...")
    consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
    try:
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")

    finally:
        logger.info("Stopping publisher...")
        publisher.stop()


if __name__ == "__main__":
    main()