import redis
import json
import time
import logging
from collections import defaultdict
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_TIMEOUT

logger = logging.getLogger("redis_manager")

class RedisManager:
    def __init__(self, redis_host=REDIS_HOST, redis_port=REDIS_PORT, 
                 redis_db=REDIS_DB, redis_timeout=REDIS_TIMEOUT):
        """Inicializa la conexión a Redis y proporciona métodos para guardar/cargar datos"""
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_timeout=redis_timeout,
            socket_connect_timeout=10,
            health_check_interval=30,
            retry_on_timeout=True,
            retry=redis.retry.Retry(max_attempts=3)
        )
        logger.info(f"Conexión a Redis establecida: {redis_host}:{redis_port}, "
                   f"timeout: {redis_timeout}s")
    
    def save_camera_data(self, camera_id, vehicles_data):
        """Guarda los datos de una cámara específica en Redis"""
        try:
            # Convertir dict a un formato compatible con JSON (si es necesario)
            vehicles_dict = dict(vehicles_data)
            
            # Serializar a JSON
            vehicles_json = json.dumps(vehicles_dict)
            
            # Guardar datos de esta cámara en su propia clave
            redis_key = f'camera:{camera_id}'
            self.redis.set(redis_key, vehicles_json)
            
            # Añadir camera_id a la lista de cámaras
            self.redis.sadd('cameras:list', camera_id)
            
            # Actualizar estadísticas
            stats = {
                "last_update": int(time.time()),
                "camera_count": len(self.get_all_cameras()),
                "vehicle_count": len(vehicles_dict)
            }
            # Convertir los valores a strings para Redis HMSET
            stats = {k: str(v) for k, v in stats.items()}
            self.redis.hmset(f'camera:{camera_id}:stats', stats)
            
            logger.info(f"Datos guardados en Redis para cámara {camera_id}: "
                       f"{len(vehicles_dict)} vehículos")
            
            return True
        except Exception as e:
            logger.error(f"Error guardando datos de cámara {camera_id} en Redis: {str(e)}")
            return False
    
    def load_camera_data(self, camera_id):
        """Carga los datos de una cámara específica desde Redis"""
        try:
            redis_key = f'camera:{camera_id}'
            camera_data = self.redis.get(redis_key)
            
            if camera_data:
                # Deserializar JSON
                vehicle_dict = json.loads(camera_data.decode('utf-8'))
                logger.info(f"Datos cargados para cámara {camera_id}: {len(vehicle_dict)} vehículos")
                return vehicle_dict
            else:
                logger.info(f"No se encontraron datos para la cámara {camera_id}")
                return {}
        except Exception as e:
            logger.error(f"Error cargando datos de cámara {camera_id}: {str(e)}")
            return {}
    
    def get_all_cameras(self):
        """Obtiene la lista de todas las cámaras registradas"""
        try:
            cameras = self.redis.smembers('cameras:list')
            return [cam.decode() for cam in cameras]
        except Exception as e:
            logger.error(f"Error obteniendo lista de cámaras: {str(e)}")
            return []
    
    def load_all_cameras_data(self):
        """Carga los datos de todas las cámaras para reconstruir el vehicle_registry completo"""
        try:
            # Obtener lista de cámaras
            cameras = self.get_all_cameras()
            
            # Reconstruir el diccionario completo
            all_data = defaultdict(dict)
            for camera_id in cameras:
                camera_data = self.load_camera_data(camera_id)
                if camera_data:  # Solo incluir si hay datos
                    all_data[camera_id] = camera_data
            
            total_vehicles = sum(len(cam_data) for cam_data in all_data.values())
            logger.info(f"Cargados datos de {len(cameras)} cámaras, "
                       f"{total_vehicles} vehículos en total")
            
            return all_data
        except Exception as e:
            logger.error(f"Error cargando datos de todas las cámaras: {str(e)}")
            return defaultdict(dict)
    
    def get_camera_stats(self, camera_id=None):
        """Obtiene estadísticas para una cámara o para todo el sistema"""
        try:
            if camera_id:
                # Estadísticas para una cámara específica
                stats = self.redis.hgetall(f'camera:{camera_id}:stats')
                return {k.decode(): v.decode() for k, v in stats.items()}
            else:
                # Estadísticas generales del sistema
                cameras = self.get_all_cameras()
                total_vehicles = 0
                camera_stats = {}
                
                for cam in cameras:
                    stats = self.redis.hgetall(f'camera:{cam}:stats')
                    if stats:
                        decoded_stats = {k.decode(): v.decode() for k, v in stats.items()}
                        camera_stats[cam] = decoded_stats
                        total_vehicles += int(decoded_stats.get('vehicle_count', 0))
                
                return {
                    "total_cameras": len(cameras),
                    "total_vehicles": total_vehicles,
                    "camera_details": camera_stats
                }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {str(e)}")
            return {}