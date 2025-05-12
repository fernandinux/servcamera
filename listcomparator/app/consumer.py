from config import *
import functools
import time
import pika
from config_logger import configurar_logger
from pika.adapters.asyncio_connection import AsyncioConnection
from pika.exchange_type import ExchangeType
import json
import threading
import queue
import asyncio

logger = configurar_logger(name=NAME_LOGS_CONSUMER, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

class ExampleConsumer(object):
    EXCHANGE = EXCHANGE_IN
    EXCHANGE_TYPE = ExchangeType.fanout
    QUEUE = QUEUE_IN
    ROUTING_KEY = ''

    def __init__(self, amqp_url, message_callback=None, prefetch_count=50, worker_threads=4):
        self.should_reconnect = False
        self.was_consuming = False

        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url
        self._consuming = False
        self._prefetch_count = prefetch_count  # Aumentado para mayor throughput
        self._message_callback = message_callback
        
        # Cola y pool de trabajadores para procesamiento paralelo
        self._message_queue = queue.Queue(maxsize=5000)  # Tamaño máximo aumentado para alta carga
        self._worker_threads = worker_threads
        self._workers = []
        self._shutdown_event = threading.Event()
        
        # Cola para ACKs desde los workers al hilo principal
        self._ack_queue = asyncio.Queue(maxsize=10000)
        
        # Contador de mensajes para monitoreo de rendimiento
        self._message_counter = 0
        self._last_log_time = time.time()
        self._ack_counter = 0

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
        # Iniciar los workers antes de empezar a consumir
        self._start_worker_threads()
        # Iniciar procesador de ACKs asíncrono
        self._schedule_ack_processing() #***
        self.start_consuming()
    
    def _schedule_ack_processing(self): #adicionado
        """Programa el procesamiento periódico de ACKs pendientes"""
        self._connection.ioloop.call_later(0.1, self._process_acks)
    
    async def _process_ack_async(self, delivery_tag):
        """Procesa un ACK de forma asíncrona"""
        try:
            self._ack_counter += 1
            self._channel.basic_ack(delivery_tag)
            return True
        except Exception as e:
            logger.error(f"Error processing ACK: {e}")
            return False
    
    def _process_acks(self):
        """Procesa los ACKs pendientes en el hilo principal"""
        if self._closing or not self._channel:
            return
        
        acks_processed = 0
        max_acks_per_iteration = 100  # Limitar cantidad de ACKs procesados por iteración
        
        # Procesar ACKs pendientes
        for _ in range(max_acks_per_iteration):
            try:
                # Intentar obtener un ACK de la cola sin bloquear
                if self._ack_queue.qsize() > 0:
                    delivery_tag = self._ack_queue.get_nowait()
                    try:
                        self._channel.basic_ack(delivery_tag)
                        acks_processed += 1
                    except Exception as e:
                        logger.error(f"Error processing ACK: {e}")
                else:
                    break  # Salir del ciclo si no hay más ACKs pendientes
            except asyncio.QueueEmpty:
                break  # Salir del ciclo si la cola está vacía
            except Exception as e:
                logger.error(f"Error getting ACK from queue: {e}")
                break
        
        # Loguear estadísticas periódicamente
        current_time = time.time()
        if current_time - self._last_log_time >= 10:  # Cada 10 segundos
            queue_size = self._ack_queue.qsize()
            msg_queue_size = self._message_queue.qsize()
            logger.info(f"ACK stats: processed={acks_processed}, pending={queue_size}, messages_queue={msg_queue_size}")
            self._last_log_time = current_time
        
        # Programar la próxima ejecución
        if not self._closing:
            # Ajustar la frecuencia según la carga
            delay = 0.01 if self._ack_queue.qsize() > 100 else 0.1
            self._connection.ioloop.call_later(delay, self._process_acks)
    
    def _start_worker_threads(self):
        """Inicia los hilos de trabajo para procesamiento paralelo"""
        logger.info(f'Starting {self._worker_threads} worker threads')
        self._workers = []
        
        for i in range(self._worker_threads):
            worker = threading.Thread(
                target=self._worker_thread_func,
                args=(i,),
                daemon=True
            )
            self._workers.append(worker)
            worker.start()
    
    def _worker_thread_func(self, worker_id):
        """Función que ejecuta cada worker thread"""
        logger.info(f'Worker thread {worker_id} started')
        msgs_processed = 0
        while not self._shutdown_event.is_set():
            try:
                # Intentar obtener un mensaje de la cola con timeout
                task = self._message_queue.get(timeout=0.5)
                if task is None:  # Señal de finalización
                    break
                    
                channel, method, properties, body, delivery_tag = task
                
                try:
                    # Procesar el mensaje
                    if self._message_callback:
                        self._message_callback(channel, method, properties, body)
                    
                    # Poner el delivery_tag en la cola de ACKs para que el loop principal los procese
                    # No usamos add_callback_threadsafe
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Usar un timeout pequeño para evitar bloqueos
                        future = asyncio.run_coroutine_threadsafe(
                            self._ack_queue.put(delivery_tag), 
                            self._connection.ioloop
                        )
                        # Esperar con timeout
                        future.result(timeout=0.5)
                    except Exception as e:
                        logger.error(f"Worker {worker_id} error enqueuing ACK: {str(e)}")
                        # Si falla encolar, intentar rechazar directamente
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                self._reject_message_async(delivery_tag), 
                                self._connection.ioloop
                            )
                            future.result(timeout=0.5)
                        except:
                            pass
                    finally:
                        loop.close()
                    
                    msgs_processed += 1
                    # Log periódico de rendimiento por worker
                    if msgs_processed % 100 == 0:
                        logger.debug(f"Worker {worker_id} processed {msgs_processed} messages")
                        
                except Exception as e:
                    logger.error(f'Worker {worker_id} error processing message: {str(e)}')
                    # Rechazar el mensaje en caso de error
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self._reject_message_async(delivery_tag), 
                            self._connection.ioloop
                        )
                        future.result(timeout=0.5)
                    except Exception as e:
                        logger.error(f"Worker {worker_id} error rejecting message: {str(e)}")
                    finally:
                        loop.close()
                finally:
                    self._message_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f'Worker {worker_id} unexpected error: {str(e)}')
                time.sleep(0.1)  # Evitar consumo excesivo de CPU en caso de error
                
        logger.info(f'Worker thread {worker_id} stopped after processing {msgs_processed} messages')
    
    async def _reject_message_async(self, delivery_tag, requeue=False):
        """Rechaza un mensaje de forma asíncrona"""
        try:
            self._channel.basic_reject(delivery_tag, requeue=requeue)
            return True
        except Exception as e:
            logger.error(f"Error rejecting message: {e}")
            return False

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

    def on_message(self, channel, basic_deliver, properties, body):
        try:
            # Incrementar contador de mensajes
            self._message_counter += 1
            
            # Log periódico de rendimiento global
            current_time = time.time()
            if self._message_counter % 1000 == 0 or current_time - self._last_log_time >= 60:
                logger.info(f"Processed {self._message_counter} messages, ACKs: {self._ack_counter}")
                self._last_log_time = current_time
            
            data = json.loads(body)
            camera_id = data.get(DATA_CAMERA)
        
            # Log: Mensaje recibido (log reducido para alta carga)
            logger.debug(f"Received message from camera {camera_id}")

            # ADICIÓN: Log detallado del mensaje completo (solo para uno de cada 20 mensajes para no saturar los logs)**
            if camera_id and int(camera_id) % 20 == 0:  # Solo para aproximadamente 5% de los mensajes
            # Formatear el JSON para mejor legibilidad
                formatted_json = json.dumps(data, indent=2)
                logger.info(f"Muestra de mensaje de la cámara {camera_id}:\n{formatted_json}")

            # Filtro inicial más estricto
            if not all(k in data for k in (DATA_CAMERA, DATA_OBJETOS_DICT)):
                logger.debug("Mensaje incompleto - Descartando")
                self._channel.basic_ack(basic_deliver.delivery_tag)  # No reintentar
                return
            
            # Poner el mensaje en la cola para procesamiento paralelo
            delivery_tag = basic_deliver.delivery_tag
            try:
                # Intenta agregar a la cola con timeout para evitar bloqueos
                self._message_queue.put(
                    (channel, basic_deliver, properties, body, delivery_tag),
                    timeout= 2.0  # 1 segundo de timeout  **
                )
            except queue.Full:
                logger.warning("Message queue full, rejecting message")
                # Si la cola está llena, rechazar el mensaje para retentarlo después
                self._channel.basic_reject(delivery_tag, requeue=True)
        
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando JSON: {str(e)}")
            self._channel.basic_reject(basic_deliver.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error en on_message: {str(e)}")
            self._channel.basic_reject(basic_deliver.delivery_tag, requeue=True)

    def stop_consuming(self):
        if self._channel:
            logger.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            cb = functools.partial(self.on_cancelok, userdata=self._consumer_tag)
            self._channel.basic_cancel(self._consumer_tag, cb)
        
        # Detener los worker threads
        self._shutdown_worker_threads()

    def _shutdown_worker_threads(self):
        """Detiene correctamente los hilos de trabajo"""
        logger.info('Shutting down worker threads')
        self._shutdown_event.set()
        
        # Agregar señales de finalización a la cola
        for _ in range(self._worker_threads):
            try:
                self._message_queue.put(None, timeout=0.5)
            except queue.Full:
                pass
        
        # Esperar a que los hilos terminen (con timeout)
        for i, worker in enumerate(self._workers):
            worker.join(timeout=2.0)
            if worker.is_alive():
                logger.warning(f'Worker thread {i} did not terminate cleanly')

    def on_cancelok(self, _unused_frame, userdata):
        self._consuming = False
        logger.info('RabbitMQ acknowledged the cancellation of the consumer: %s',
                    userdata)
        self.close_channel()

    def close_channel(self):
        logger.info('Closing the channel')
        self._channel.close()

    def run(self):
        logger.info('Starting IOLoop')
        self._connection = self.connect()
        self._connection.ioloop.run_forever()
        logger.info('IOLoop stopped')

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
    def __init__(self, amqp_url, message_callback=None, exchange=EXCHANGE_IN, queue=QUEUE_IN, 
                 prefetch_count=50, worker_threads=4):
        self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._consumer = ExampleConsumer(
            self._amqp_url, 
            message_callback=message_callback, 
            prefetch_count=prefetch_count,
            worker_threads=worker_threads
        )
        
        # Permitir customizar exchange y queue
        self._consumer.EXCHANGE = exchange
        self._consumer.QUEUE = queue

    def run(self):
        while True:
            try:
                logger.info(f"Conectando a {self._amqp_url}...")
                self._consumer.run()
            except KeyboardInterrupt:
                logger.info("Detenido por usuario")
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            logger.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = ExampleConsumer(
                self._amqp_url, 
                message_callback=self._consumer._message_callback,
                prefetch_count=self._consumer._prefetch_count,
                worker_threads=self._consumer._worker_threads
            )
            self._consumer.EXCHANGE = self._consumer.EXCHANGE
            self._consumer.QUEUE = self._consumer.QUEUE

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay
        
    def stop(self):
        """Detiene el consumidor de forma segura"""
        logger.info("Deteniendo ReconnectingExampleConsumer")
        if self._consumer:
            self._consumer.stop()