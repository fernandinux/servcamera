from config import *

import functools
import time
import pika  # type: ignore
from config import *
from config_logger import configurar_logger

from pika.adapters.asyncio_connection import AsyncioConnection  # type: ignore
from pika.exchange_type import ExchangeType  # type: ignore

# logger = logging.getLogger(name=NAME_LOGS)
logger = configurar_logger(name=NAME_LOGS_CONSUMER, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)


class ExampleConsumer(object):
    """Consumer de ejemplo para RabbitMQ.
    
    Ahora permite inyectar una función de _callback_ para procesar cada mensaje.
    """
    EXCHANGE = EXCHANGE_IN
    EXCHANGE_TYPE = ExchangeType.fanout
    QUEUE = QUEUE_IN
    ROUTING_KEY = ''

    def __init__(self, amqp_url, message_callback=None):
        """Inicializa el consumidor.

        :param str amqp_url: URL AMQP para conectarse a RabbitMQ.
        :param callable message_callback: Función a la que se le pasará el mensaje
               recibido, con la siguiente firma:
               callback(channel, basic_deliver, properties, body)
        """
        self.should_reconnect = False
        self.was_consuming = False

        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url
        self._consuming = False
        self._prefetch_count = 1
        self._message_callback = message_callback

    def connect(self):
        logger.info('Connecting to %s', self._url)
        return AsyncioConnection(
            parameters=pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed)

    def close_connection(self):
        self._consuming = False
        if self._connection.is_closing or self._connection.is_closed:
            logger.info('Connection is closing or already closed')
        else:
            logger.info('Closing connection')
            self._connection.close()

    def on_connection_open(self, _unused_connection):
        logger.info('Connection opened')
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        logger.error('Connection open failed: %s', err)
        self.reconnect()

    def on_connection_closed(self, _unused_connection, reason):
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            logger.warning('Connection closed, reconnect necessary: %s', reason)
            self.reconnect()

    def reconnect(self):
        self.should_reconnect = True
        self.stop()

    def open_channel(self):
        logger.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        logger.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def add_on_channel_close_callback(self):
        logger.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        logger.warning('Channel %i was closed: %s', channel, reason)
        self.close_connection()

    def setup_exchange(self, exchange_name):
        logger.info('Declaring exchange: %s', exchange_name)
        cb = functools.partial(self.on_exchange_declareok, userdata=exchange_name)
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=self.EXCHANGE_TYPE,
            durable=True,
            callback=cb)

    def on_exchange_declareok(self, _unused_frame, userdata):
        logger.info('Exchange declared: %s', userdata)
        self.setup_queue(self.QUEUE)

    def setup_queue(self, queue_name):
        logger.info('Declaring queue %s', queue_name)
        cb = functools.partial(self.on_queue_declareok, userdata=queue_name)
        self._channel.queue_declare(queue=queue_name, durable=True, callback=cb)

    def on_queue_declareok(self, _unused_frame, userdata):
        queue_name = userdata
        logger.info('Binding %s to %s with %s', self.EXCHANGE, queue_name,
                    self.ROUTING_KEY)
        cb = functools.partial(self.on_bindok, userdata=queue_name)
        self._channel.queue_bind(
            queue_name,
            self.EXCHANGE,
            routing_key=self.ROUTING_KEY,
            callback=cb)

    def on_bindok(self, _unused_frame, userdata):
        logger.info('Queue bound: %s', userdata)
        self.set_qos()

    def set_qos(self):
        self._channel.basic_qos(
            prefetch_count=self._prefetch_count, callback=self.on_basic_qos_ok)

    def on_basic_qos_ok(self, _unused_frame):
        logger.info('QOS set to: %d', self._prefetch_count)
        self.start_consuming()

    def start_consuming(self):
        logger.info('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(
            self.QUEUE, self.on_message)
        self.was_consuming = True
        self._consuming = True

    def add_on_cancel_callback(self):
        logger.info('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        logger.info('Consumer was cancelled remotely, shutting down: %r',
                    method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, _unused_channel, basic_deliver, properties, body):
        logger.info('Received message # %s from %s: %s',
                    basic_deliver.delivery_tag, properties.app_id, body)
        if self._message_callback:
            try:
                self._message_callback(_unused_channel, basic_deliver, properties, body)
            except Exception as e:
                logger.error("Error in message callback: %s", e)
        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag):
        logger.info('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        if self._channel:
            logger.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            cb = functools.partial(self.on_cancelok, userdata=self._consumer_tag)
            self._channel.basic_cancel(self._consumer_tag, cb)

    def on_cancelok(self, _unused_frame, userdata):
        self._consuming = False
        logger.info('RabbitMQ acknowledged the cancellation of the consumer: %s',
                    userdata)
        self.close_channel()

    def close_channel(self):
        logger.info('Closing the channel')
        self._channel.close()

    def run(self):
        self._connection = self.connect()
        self._connection.ioloop.run_forever()

    def stop(self):
        if not self._closing:
            self._closing = True
            logger.info('Stopping')
            if self._consuming:
                self.stop_consuming()
                self._connection.ioloop.run_forever()
            else:
                self._connection.ioloop.stop()
            logger.info('Stopped')


class ReconnectingExampleConsumer(object):
    """Consumer que se reconecta si es necesario."""
    def __init__(self, amqp_url, message_callback=None):
        self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._consumer = ExampleConsumer(self._amqp_url, message_callback=message_callback)

    def run(self):
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            logger.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = ExampleConsumer(self._amqp_url, message_callback=self._consumer._message_callback)

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay


def main():
    import sys
    amqp_url = 'amqp://guest:guest@localhost:5672/%2F'
    consumer = ReconnectingExampleConsumer(amqp_url)
    consumer.run()


if __name__ == '__main__':
    main()
