import redis
import json
import time
from config_logger import configurar_logger
from config import *
import threading

logger = configurar_logger(name="processing", log_dir=LOG_DIR, nivel=LOGGING_CONFIG)
#logger = logging.getLogger(NAME_LOGS)

class StolenVehicleDetector:
    def __init__(self):
        """
        Inicializa el detector de vehículos robados con optimizaciones para alta carga.
        """
        logger.info("Inicializando detector de vehículos robados...")
        
        # Hash principal para todas las placas en todas las listas
        self.main_hash = "list_comparator"

        # Prefijo para los conjuntos de cada tipo de lista
        self.list_set_prefix = "list_comparator:"
        
        # Conexión a Redis con pool de conexiones
        self._setup_redis_connection()

        # Obtener los tipos de listas disponibles
        self._update_list_types()
        
        # Caché local para placas robadas con TTL
        self.cache_lock = threading.RLock()
        self.plate_cache = {}
        self.cache_timestamp = {}
        self.cache_ttl = 300  # 5 minutos (ajustar según necesidad)
        
        # Sistema de control de alertas para evitar duplicados
        self.alert_lock = threading.RLock()
        self.recent_alerts = {}
        self.alert_cooldown = 3600  # Tiempo en segundos entre alertas del mismo vehículo
        
        # Contador para estadísticas y monitoreo
        self.stats = {
            "processed_plates": 0,
            "cache_hits": 0,
            "redis_queries": 0,
            "alerts_by_list": {},
            "alerts_suppressed": 0  # Contador para alertas suprimidas
        }
        self.stats_lock = threading.RLock()

        # Timer para actualización periódica de listas
        self._setup_refresh_timer()

    def _setup_redis_connection(self):
        """
        Establece la conexión con Redis usando un pool de conexiones.
        """
        try:
            # Crear pool de conexiones para Redis
            self.redis_pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                socket_timeout=REDIS_TIMEOUT,
                max_connections=10  # Ajustar según carga esperada
            )
            self.redis_client = redis.Redis(connection_pool=self.redis_pool)
            logger.info(f"Pool de conexiones a Redis establecido: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.error(f"Error al conectar con Redis: {str(e)}")
            raise

    def _setup_refresh_timer(self):
        """Configura un timer para actualizar periódicamente las listas disponibles"""
        self.refresh_interval = 300  # 5 minutos
        self.refresh_timer = threading.Timer(self.refresh_interval, self._periodic_refresh)
        self.refresh_timer.daemon = True
        self.refresh_timer.start()


    def _periodic_refresh(self):
        """Actualiza periódicamente las listas y reinicia el timer"""
        try:
            self._update_list_types()
        except Exception as e:
            logger.error(f"Error actualizando tipos de listas: {str(e)}")
        finally:
            # Reiniciar el timer
            self.refresh_timer = threading.Timer(self.refresh_interval, self._periodic_refresh)
            self.refresh_timer.daemon = True
            self.refresh_timer.start()

    def _update_list_types(self):
        """
        Descubre dinámicamente los tipos de listas disponibles
        buscando los conjuntos que comienzan con el prefijo definido.
        """
        try:
            # Patrón para buscar todos los conjuntos de listas
            pattern = f"{self.list_set_prefix}*"
            
            # Obtener todas las claves que coinciden con el patrón
            all_keys = set()
            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
                all_keys.update([k.decode('utf-8') for k in keys])
                if cursor == 0:
                    break
            
            # Extraer los tipos de listas de las claves de los conjuntos
            self.list_types = [k.replace(self.list_set_prefix, '') for k in all_keys]
            
            # Si hay listas nuevas, actualizar estadísticas
            with self.stats_lock:
                for list_type in self.list_types:
                    if list_type not in self.stats["alerts_by_list"]:
                        self.stats["alerts_by_list"][list_type] = 0
            
            logger.info(f"Tipos de listas actualizados: {len(self.list_types)} listas encontradas")
            logger.debug(f"Listas disponibles: {self.list_types}")
            
            return True
        except Exception as e:
            logger.error(f"Error al descubrir tipos de listas: {str(e)}")
            return False
        
    
    def _get_license_plate_from_data(self, data):
        """
        Extrae la información de las placas del diccionario de objetos.
        Ajustado para procesar el formato real de los datos recibidos.
        
        Args:
            data (dict): Mensaje completo recibido con el formato correcto.
                
        Returns:
            list: Lista de diccionarios con la información de las placas detectadas.
        """
        license_plates = []
        
        try:
            # Obtener el diccionario de objetos
            object_dict = data.get(DATA_OBJETOS_DICT, {})
            
            # Iterar por categorías y objetos
            for category, objects in object_dict.items():
                for obj in objects:
                    # Obtener la descripción que contiene el texto de la placa
                    plate_text = obj.get('description')


                    # Filtrar solo los objetos con attribute_id=1 (placas vehiculares)
                    if plate_text and obj.get('attribute_id') == 1:
                        plate_info = {}
                        plate_info['id_tracking'] = obj.get('id_tracking')
                        plate_info['coords'] = obj.get('coords')
                        plate_info['epoch_object'] = obj.get('epoch_object')
                        plate_info['object_id'] = obj.get('object_id')
                        plate_info['category'] = category
                        plate_info['plate_text'] = plate_text
                        plate_info['accuracy'] = obj.get('accuracy_attribute', 0)
                        plate_info['init_time'] = obj.get('init_time', 0)
                        plate_info['final_time'] = obj.get('final_time', 0)
                        
                        license_plates.append(plate_info)
            
            # Actualizar estadísticas
            with self.stats_lock:
                self.stats["processed_plates"] += len(license_plates)
            
            # Log para depuración
            if license_plates:
                logger.info(f"Se encontraron {len(license_plates)} placas para verificar: {[p['plate_text'] for p in license_plates]}")
            
            return license_plates
        
        except Exception as e:
            logger.error(f"Error al extraer información de las placas: {str(e)}")
            return []
    
    def _check_plate_in_lists(self, plate_text):
        """
        Verifica si una placa está en alguna de las listas de monitoreo.
        
        Args:
            plate_text (str): Texto de la placa a verificar.
            
        Returns:
            tuple: (is_found, list_type, vehicle_data) - Indica si la placa se encontró,
                  en qué lista y la información adicional.
        """
        # Normalizar placa
        if not plate_text:
            return False, None, None
            
        normalized_plate = plate_text.strip().upper()
        
        # Verificar en caché primero
        with self.cache_lock:
            current_time = time.time()
            if normalized_plate in self.plate_cache:
                # Verificar si la entrada de caché es válida
                if current_time - self.cache_timestamp.get(normalized_plate, 0) < self.cache_ttl:
                    # Incrementar contador de cache hits
                    with self.stats_lock:
                        self.stats["cache_hits"] += 1
                    return self.plate_cache[normalized_plate]
                else:
                    # Caché expirado, eliminar
                    del self.plate_cache[normalized_plate]
                    if normalized_plate in self.cache_timestamp:
                        del self.cache_timestamp[normalized_plate]
        
        # No está en caché o caché expirado, consultar Redis
        try:
            with self.stats_lock:
                self.stats["redis_queries"] += 1


            # ¿Necesitamos actualizar la lista de tipos?
            if not hasattr(self, 'list_types') or not self.list_types:
                self._update_list_types()

            # Verificar en cada uno de los tipos de listas
            for list_type in self.list_types:
                # Formar la clave compuesta para el hash
                field_key = f"{list_type}:{normalized_plate}"

                #Verificar si existe en el hash principal
                exists = self.redis_client.hexists(self.main_hash, field_key)

                if exists:
                    #Obtener info adicional
                    vehicle_info = self.redis_client.hget(self.main_hash, field_key)
                    if vehicle_info:
                        try:
                            vehicle_data = json.loads(vehicle_info)
                        except:
                            vehicle_data = {"status": list_type}
                    else:
                        vehicle_data = {"status": list_type}
                    
                    # Incluir el tipo de lista en los datos
                    vehicle_data["list_type"] = list_type
                    
                    # Guardar en caché
                    with self.cache_lock:
                        self.plate_cache[normalized_plate] = (True, list_type, vehicle_data)
                        self.cache_timestamp[normalized_plate] = time.time()
                    
                    return True, list_type, vehicle_data
            
            # No se encontró en ninguna lista
            with self.cache_lock:
                self.plate_cache[normalized_plate] = (False, None, None)
                self.cache_timestamp[normalized_plate] = time.time()
            
            return False, None, None
                
        except Exception as e:
            logger.error(f"Error al verificar placa en Redis: {str(e)}")
            # En caso de error, devolver que no está en ninguna lista
            return False, None, None
    
    def _check_monitored_plates(self, license_plates, camera_id):
        """
        Compara las placas detectadas con todas las listas de monitoreo,
        evitando alertas duplicadas en períodos cortos de tiempo.
        
        Args:
            license_plates (list): Lista de diccionarios con información de placas.
            camera_id (str): ID de la cámara que realizó la detección.
            
        Returns:
            list: Lista de placas que coinciden con alguna lista de monitoreo.
        """
        alerts = []
        current_time = time.time()
        
        try:
            for plate_info in license_plates:
                plate_text = plate_info.get('plate_text')
                if not plate_text:
                    continue
                
                normalized_plate = plate_text.strip().upper()
                is_found, list_type, vehicle_data = self._check_plate_in_lists(plate_text)
                
                if is_found and list_type:
                    # Crear identificador único para este vehículo en esta cámara y lista
                    alert_key = f"{normalized_plate}_{camera_id}_{list_type}"
                    
                    # Verificar si ya se alertó recientemente sobre esta placa en esta cámara
                    with self.alert_lock:
                        last_alert_time = self.recent_alerts.get(alert_key, 0)


                        if current_time - last_alert_time >= self.alert_cooldown:
                            # Crear la alerta con los campos en el nivel adecuado
                            alert = {
                                # Campos de primer nivel necesarios
                                'id_tracking': plate_info.get('id_tracking'),
                                #'coords': plate_info.get('coords'),
                                'object_id' : plate_info.get('object_id'),
                                'epoch_object': plate_info.get('epoch_object'),
                                'plate_text': plate_text,
                                'timestamp': int(current_time),
                                'camera_id': camera_id,
                                #'list_type': list_type,
                                'alert_type': list_type,
                                # Agregar 'epoch_frame'

                                # Determinar categoría y tipo según la lista
                                'category': 2 if list_type == "robados" else 1,
                                'type': 6, #if list_type == "robados" else 7,
                                
                                # Personalizar el mensaje según el tipo de lista
                                'message': f"Vehiculo de lista '{list_type.replace('_', ' ')}' detectado en camara {camera_id}",
                                
                                # Mantener vehicle_info como objeto anidado
                                'vehicle_info': vehicle_data
                            }
                            
                            # Agregar otros campos de plate_info que puedan ser relevantes
                            for key in ['accuracy', 'init_time', 'final_time']:
                                if key in plate_info:
                                    alert[key] = plate_info[key]
                            
                            alerts.append(alert)
                            logger.info(f"Vehículo de la lista '{list_type}' detectado: {plate_text} en cámara {camera_id}")
                            
                            # Actualizar tiempo de última alerta
                            self.recent_alerts[alert_key] = current_time
                            
                            with self.stats_lock:
                                self.stats["alerts_by_list"][list_type] = self.stats["alerts_by_list"].get(list_type, 0) + 1
                        else:
                            # Alerta suprimida por estar en período de enfriamiento
                            logger.debug(f"Alerta suprimida para vehículo {plate_text} (lista: {list_type}) en cámara {camera_id} (en período de enfriamiento)")
                            with self.stats_lock:
                                self.stats["alerts_suppressed"] += 1
        
        except Exception as e:
            logger.error(f"Error al verificar placas monitoreadas: {str(e)}")
        
        return alerts
    
    def process(self, camera_id, data):
        """
        Procesa los datos recibidos para detectar vehículos en todas las listas de monitoreo.
        
        Args:
            camera_id (str): ID de la cámara.
            data (dict): Diccionario con la información de los objetos detectados.
            
        Returns:
            list: Lista de alertas de vehículos monitoreados.
        """
        start_time = time.time()
        #processing_times = {}

        try:
            # Extraer información de las placas
            license_plates = self._get_license_plate_from_data(data)
            
            if not license_plates:
                logger.debug(f"No se encontraron placas en la detección de la cámara {camera_id}")
                return []
            
            logger.debug(f"Se encontraron {len(license_plates)} placas en la cámara {camera_id}")
            
            # Verificar si alguna placa corresponde a un vehículo monitoreado
            # y generar alertas completas directamente
            alerts = self._check_monitored_plates(license_plates, camera_id)
            
            # Cada 100 procesamientos, mostrar estadísticas
            with self.stats_lock:
                if self.stats["processed_plates"] % 100 == 0:
                    logger.info(f"Estadísticas de procesamiento: {self.stats}")
            
            end_time = time.time()
            processing_time = round((end_time - start_time) * 1000, 2)
            logger.debug(f"Tiempo de procesamiento: {processing_time} ms")
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error en el procesamiento de detección: {str(e)}")
            return []
    
    def cleanup_cache(self):
        """
        Limpia entradas antiguas de la caché para evitar consumo excesivo de memoria.
        Se puede llamar periódicamente si es necesario.
        """
        logger.debug("Limpiando caché de placas...")
        with self.cache_lock:
            current_time = time.time()
            expired_keys = []
            
            # Identificar entradas expiradas
            for plate, timestamp in self.cache_timestamp.items():
                if current_time - timestamp > self.cache_ttl:
                    expired_keys.append(plate)
            
            # Eliminar entradas expiradas
            for plate in expired_keys:
                if plate in self.plate_cache:
                    del self.plate_cache[plate]
                if plate in self.cache_timestamp:
                    del self.cache_timestamp[plate]
            
            logger.debug(f"Se eliminaron {len(expired_keys)} entradas expiradas de la caché")

    def cleanup_alerts(self):
        """
        Limpia entradas antiguas del registro de alertas recientes.
        Se puede llamar periódicamente para evitar consumo excesivo de memoria.
        """
        logger.debug("Limpiando registro de alertas recientes...")
        with self.alert_lock:
            current_time = time.time()
            expired_keys = []
            
            # Identificar entradas expiradas (con el doble del tiempo de enfriamiento)
            for alert_key, timestamp in self.recent_alerts.items():
                if current_time - timestamp > self.alert_cooldown * 2:
                    expired_keys.append(alert_key)
            
            # Eliminar entradas expiradas
            for alert_key in expired_keys:
                if alert_key in self.recent_alerts:
                    del self.recent_alerts[alert_key]
            
            logger.debug(f"Se eliminaron {len(expired_keys)} entradas expiradas del registro de alertas")