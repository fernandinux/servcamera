# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205

import functools
import logging
from config import *
from config_logger import configurar_logger
import json
import pika # type: ignore
from pika.exchange_type import ExchangeType # type: ignore
import threading
import time
# logger = configurar_logger(name=NAME_LOGS_PUBLISHER, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)
logger = configurar_logger(name=NAME_LOGS_PUBLISHER, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class ExamplePublisher(object):
    """
    Publicador asíncrono que maneja interacciones inesperadas con RabbitMQ,
    tales como cierres de canal o conexión. En este ejemplo se declara únicamente
    un exchange de tipo direct (objs_candidate). No se declara ninguna cola,
    ya que serán los consumidores quienes creen y enlacen sus propias colas.
    """
    EXCHANGE = EXCHANGE_OUT
    EXCHANGE_TYPE = ExchangeType.fanout
    ROUTING_KEY = ''

    def __init__(self, amqp_url):
        """
        Inicializa el publicador con la URL de conexión a RabbitMQ.
        """
        self._url = amqp_url
        self._connection = None
        self._channel = None
        self._sync_lock = threading.Lock()
        self._stats = {
            'messages_received': 0,
            'messages_published': 0,
            'messages_filtered': 0
        }

        self._deliveries = {}
        self._acked = 0
        self._nacked = 0
        self._message_number = 0
        self._stopping = False
        self._thread = None
        self.EXCHANGE = 'alert_details'  # CORROBORAR **

    def connect(self):
        """
        Conecta a RabbitMQ y retorna el objeto SelectConnection.
        """
        logger.info("Connecting to %s", self._url)
        
        return pika.SelectConnection(
            pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed
        )

    def on_connection_open(self, _unused_connection):
        """
        Callback cuando se establece la conexión.
        """
        logger.info("Connection opened")
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        """
        Callback en caso de fallo al conectar.
        """
        logger.error("Connection open failed: %s", err)
        self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def on_connection_closed(self, _unused_connection, reason):
        """
        Callback cuando la conexión se cierra inesperadamente.
        """
        logger.warning("Connection closed: %s", reason)
        self._channel = None
        if self._stopping:
            self._connection.ioloop.stop()
        else:
            logger.warning("Reconnecting in 5 seconds")
            self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def open_channel(self):
        """
        Abre un nuevo canal en la conexión.
        """
        logger.info("Creating a new channel")
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        """
        Callback cuando el canal se abre.
        """
        logger.info("Channel opened")
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def add_on_channel_close_callback(self):
        """
        Configura el callback de cierre del canal.
        """
        logger.info("Adding channel close callback")
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        """
        Callback cuando el canal se cierra inesperadamente.
        """
        logger.warning("Channel %i closed: %s", channel, reason)
        self._channel = None
        if not self._stopping:
            self._connection.close()

    def setup_exchange(self, exchange_name):
        """
        Declara el exchange en RabbitMQ.
        """
        logger.info("Declaring exchange %s", exchange_name)
        cb = functools.partial(self.on_exchange_declareok, userdata=exchange_name)
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=self.EXCHANGE_TYPE,
            durable=True,
            callback=cb
        )

    def on_exchange_declareok(self, _unused_frame, userdata):
        """
        Callback cuando se confirma la declaración del exchange.
        """
        logger.info("Exchange declared: %s. Publisher is ready.", userdata)
        self.enable_delivery_confirmations()

    def enable_delivery_confirmations(self):
        """
        Habilita las confirmaciones de entrega para los mensajes publicados.
        """
        logger.info("Enabling delivery confirmations")
        self._channel.confirm_delivery(self.on_delivery_confirmation)

    def on_delivery_confirmation(self, method_frame):
        """
        Callback cuando RabbitMQ confirma (ack/nack) la entrega de un mensaje.
        """
        confirmation_type = method_frame.method.NAME.split('.')[1].lower()
        ack_multiple = method_frame.method.multiple
        delivery_tag = method_frame.method.delivery_tag

        logger.info("Received %s for delivery tag: %i (multiple: %s)",
                    confirmation_type, delivery_tag, ack_multiple)

        if confirmation_type == 'ack':
            self._acked += 1
        elif confirmation_type == 'nack':
            self._nacked += 1

        if delivery_tag in self._deliveries:
            del self._deliveries[delivery_tag]

        if ack_multiple:
            for tmp_tag in list(self._deliveries.keys()):
                if tmp_tag <= delivery_tag:
                    self._acked += 1
                    del self._deliveries[tmp_tag]

        logger.info("Published %i messages, %i unconfirmed, %i acked, %i nacked",
                    self._message_number, len(self._deliveries), self._acked, self._nacked)

    def publish_async(self, message, exchange=None, routing_key='', headers=None):
        """
        Publica un mensaje de forma asíncrona.
        Puede ser llamado desde cualquier hilo, ya que utiliza add_callback_threadsafe().

        :param message: Objeto que se serializará a JSON.
        :param routing_key: (Opcional) Routing key. Por defecto se usa self.ROUTING_KEY.
        :param headers: (Opcional) Diccionario de headers.
        """
        if exchange is None:
            exchange = self.EXCHANGE  # Usa el exchange por defecto si no se especifica

        if not self._channel or not self._channel.is_open:
            logger.error("Canal no disponible para publicar")
            return
        # if routing_key is None:
        #     routing_key = self.ROUTING_KEY
        # if headers is None:
        #     headers = {u'مفتاح': u' قيمة', u'键': u'值', u'キー': u'値'}
        inicio_tiempo = time.time()
        
        def _publish():
            if self._channel and self._channel.is_open:
                properties = pika.BasicProperties(
                    app_id='example-publisher',
                    content_type='application/json',
                    headers=headers
                )
                body = json.dumps(message, ensure_ascii=False)
                try:
                    self._channel.basic_publish(
                        exchange=exchange,
                        routing_key=routing_key,
                        body=body,
                        properties=properties
                    )

                    self._message_number += 1
                    self._deliveries[self._message_number] = True
                    elapsed = time.time() - inicio_tiempo
                    logger.info(f"Published message #{self._message_number} to {exchange} in {elapsed:.4f}s")
                    #logger.info("Published message #%i in %.4f seconds", self._message_number, elapsed)
                    logger.debug(f"Message content:\n{json.dumps(message, indent=2)}")

                except Exception as e:
                    logger.error("Error publishing message: %s", e)
            else:
                logger.error("Channel is not open. Cannot publish message.")

        if self._connection and self._connection.is_open:
            self._connection.ioloop.add_callback_threadsafe(_publish)
        else:
            logger.error("Connection is not open. Cannot schedule message publication.")

    def run(self):
        """
        Ejecuta el IOLoop en un ciclo que permite reconexión en caso de desconexión.
        Este método se ejecuta en un hilo de fondo.
        """
        while not self._stopping:
            self._connection = self.connect()
            try:
                self._connection.ioloop.start()
            except Exception as e:
                logger.error("Error in IOLoop: %s", e)
        logger.info("Publisher run loop exited.")

    def start(self):
        """
        Inicia el publicador en un hilo de fondo.
        """
        self._stopping = False
        # Reinicia contadores y variables
        self._deliveries = {}
        self._acked = 0
        self._nacked = 0
        self._message_number = 0

        self._thread = threading.Thread(target=self.run, name="PublisherThread")
        self._thread.start()
        logger.info("Publisher thread started.")

    def stop(self):
        """
        Detiene el publicador cerrando el canal, la conexión y finalizando el hilo.
        """
        logger.info("Stopping publisher")
        self._stopping = True
        self.close_channel()
        self.close_connection()
        if self._connection and self._connection.is_open:
            self._connection.ioloop.stop()
        if self._thread:
            self._thread.join()
        logger.info("Publisher stopped.")

    def close_channel(self):
        """
        Cierra el canal enviando el comando Channel.Close a RabbitMQ.
        """
        if self._channel is not None:
            logger.info("Closing the channel")
            self._channel.close()

    def close_connection(self):
        """
        Cierra la conexión a RabbitMQ.
        """
        if self._connection is not None:
            logger.info("Closing connection")
            self._connection.close()


# # Si se ejecuta este módulo directamente, se puede realizar una prueba.
# if __name__ == '__main__':
#     import time

#     publisher = ExamplePublisher(
#         'amqp://guest:guest@localhost:5672/%2F?connection_attempts=3&heartbeat=3600'
#     )
#     publisher.start()

#     try:
#         # Publicar mensajes de prueba asíncronos
#         for i in range(10):
#             publisher.publish_async("Test message %d" % i)
#             time.sleep(1)
#         time.sleep(5)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         publisher.stop() 