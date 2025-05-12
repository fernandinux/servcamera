import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pytz
import os

def configurar_logger(
    name: str,
    nivel: int = logging.INFO,
    log_dir: str = "./",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 1,
    zona_horaria: str = "America/Lima"
) -> logging.Logger:
    """
    Configura un logger con rotación de archivos y zona horaria personalizada.
    
    Parámetros:
    name (str): Nombre del logger y del archivo de log
    nivel (int): Nivel de logging (ej: logging.DEBUG, logging.INFO)
    log_dir (str): Directorio para guardar los logs
    max_bytes (int): Tamaño máximo por archivo de log en bytes
    backup_count (int): Número máximo de archivos de log a mantener
    zona_horaria (str): Zona horaria para los timestamps (ej: 'America/Lima', 'Europe/Madrid')
    
    Retorna:
    logging.Logger: Logger configurado
    """
    
    class TimezoneFormatter(logging.Formatter):
        """Formateador personalizado con zona horaria"""
        def __init__(self, fmt=None, datefmt=None, tz=None):
            super().__init__(fmt, datefmt)
            self.tz = tz

        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, self.tz)
            return dt.strftime(datefmt) if datefmt else dt.isoformat()
    
    # Crear directorio si no existe
    log_file = f"{log_dir}/{name}.log"
    log_file = os.path.abspath(log_file)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Configurar handler con rotación
    log_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    
    # Configurar formateador con zona horaria
    formatter = TimezoneFormatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        tz=pytz.timezone(zona_horaria)
    )
    log_handler.setFormatter(formatter)
    
    # Crear y configurar logger
    logger = logging.getLogger(name)
    logger.setLevel(nivel)
    logger.addHandler(log_handler)
    logger.propagate = False  # Evitar logs duplicados
    
    return logger
