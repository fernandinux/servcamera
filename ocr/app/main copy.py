import os
import json
import time
import cv2
from datetime import datetime
import torch
import torch.multiprocessing as mp
from torch.multiprocessing import Pool, current_process
from paddleocr import PaddleOCR

# Importamos la configuración y las funciones de logging
from config import *
from config_logger import configurar_logger
from processor import getOCR
from consumer import ReconnectingExampleConsumer
from publisher import ExamplePublisher

# Configuración global del logger
logger = configurar_logger(name=NAME_LOGS, log_dir=LOG_DIR, nivel=LOGGING_CONFIG)

# Variables globales
publisher = None
ocr_instance = None
pool = None

def init_worker():
    """
    Inicializa el worker cargando el modelo PaddleOCR.
    """
    global ocr_instance
    try:
        worker_name = current_process().name
        logger.info(f"Inicializando modelo en el worker {worker_name}...")
        ocr_instance = PaddleOCR(
            use_angle_cls=USE_ANGLE_CLS,
            lang=OCR_LANG,
            use_gpu=USE_GPU,
            # ocr_version=OCR_VERSION,
            det_model_dir=DET_MODEL_DIR,
            rec_model_dir=REC_MODEL_DIR,
            cls_model_dir=CLS_MODEL_DIR,
            rec=False,
            show_log=False
        )
        logger.info(f"Modelo cargado en el worker {worker_name}.")
    except Exception as e:
        logger.error(f"Error inicializando worker: {e}")
        raise

def get_date(epoch: float) -> tuple:
    """
    Convierte un valor epoch en una fecha y hora formateadas.
    """
    dt = datetime.fromtimestamp(epoch)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H')

def get_folder_path(data: dict) -> str:
    """
    Genera la ruta de salida basado en la fecha y la cámara.
    """
    try:
        if DATA_EPOCH_FRAME not in data or DATA_CAMERA not in data:
            raise ValueError("Faltan campos requeridos en los datos.")
        day, hour = get_date(data[DATA_EPOCH_FRAME] / EPOCH_FRAME_FORMAT)
        output_path = os.path.join("/output", str(data[DATA_CAMERA]), day, hour)
        logger.info(f"Ruta de salida generada: {output_path}")
        os.makedirs(output_path, exist_ok=True)
        return output_path
    except Exception as e:
        logger.error(f"Error generando carpeta de salida: {e}")
        return None

def load_image(path: str) -> tuple:
    """
    Carga una imagen desde el path indicado y retorna la imagen junto con un flag de éxito.
    """
    img = cv2.imread(path)
    if img is None:
        logger.error(f"No se pudo abrir la imagen en la ruta: {path}")
        return None, False
    return img, True

def get_result_objects(model, frame, classes, conf, verbose: bool = False):
    """
    Ejecuta la predicción del modelo sobre la imagen.
    """
    return model.predict(source=frame, classes=classes, conf=conf, verbose=verbose)

def get_device() -> str:
    """
    Retorna el dispositivo (cuda o cpu) disponible.
    """
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Dispositivo seleccionado: {device}")
    return device

def process_image(file_path: str):
    """
    Procesa la imagen usando el OCR cargado en el worker.
    """
    try:
        car_image, success = load_image(file_path)
        if not success:
            return None
        # Redimensionamos la imagen (se asume que el escalado es intencional)
        car_image = cv2.resize(car_image, (0, 0), fx=2, fy=2)
        return getOCR(ocr_instance, car_image)
    except Exception as e:
        logger.error(f"Error al procesar la imagen {file_path}: {e}")
        return None

def process_plate(folder: str, box: dict):
    """
    Procesa la imagen de la placa a partir de la información contenida en 'box'.
    """
    try:
        filename = f"{box[DATA_ATRIBUTO_INIT_TIME]}.jpeg"
        plate_img_path = os.path.join(folder, "plates", filename)
        logger.info(f"Procesando imagen de placa: {plate_img_path}")
        
        # Asegurarse de que el directorio 'plates' exista
        os.makedirs(os.path.join(folder, "plates"), exist_ok=True)
        
        result = process_image(plate_img_path)
        if result is None:
            logger.warning("Placa no reconocida, retornando valores nulos.")
            return None, None, None, None

        # Se espera que getOCR retorne tres valores: descripción, accuracy y status
        description, accuracy, status = result
        logger.debug(f"Imagen procesada: {plate_img_path}")
        # Se utiliza 1000 para obtener milisegundos (ajustar si es necesario)
        return description, accuracy, status, int(time.time() * 1000)
    except Exception as e:
        logger.error(f"Error procesando la placa: {e}")
        return None, None, None, None

def process_frame(data: dict):
    """
    Procesa la imagen y actualiza la información de detección.
    Se ejecuta en un proceso separado administrado por torch.multiprocessing.
    """
    try:
        if DATA_CAMERA not in data:
            raise ValueError("El campo de cámara está ausente en los datos.")
        cam_id = data[DATA_CAMERA]
        folder_path = get_folder_path(data)
        if folder_path is None:
            raise ValueError("No se pudo obtener la ruta de salida.")
        logger.info(f"Carpeta de salida para cámara {cam_id}: {folder_path}")

        # Se asume que 'objetos' es un diccionario
        objetos = data.get(DATA_OBJESTOS_LIST, {})
        for categoria, boxes in objetos.items():
            for box in boxes:
                # Procesar solo cajas candidatas con coordenadas
                if box.get(DATA_OBJETO_CANDIDATO, False) and box.get(DATA_OBJETO_COORDS_ATTRIBUTE) is not None:
                    description, accuracy, status, final_time = process_plate(folder_path, box)
                    box[DATA_ATRIBUTO_ID] = 1
                    box[DATA_ATRIBUTO_DESCRIPITON] = description
                    box[DATA_ATRIBUTO_ACCURACY] = accuracy
                    box[DATA_ATRIBUTO_FINAL_TIME] = final_time
                    box[DATA_ATRIBUTO_STATUS] = status
        return data
    except Exception as e:
        logger.error(f"Error en el procesamiento del frame: {e}")
        return None

def rabbitmq_message_callback(channel, basic_deliver, properties, body):
    """
    Callback para cada mensaje recibido desde RabbitMQ.
    Decodifica el JSON, determina la ruta de la imagen y despacha
    la función de procesamiento al pool de workers.
    """
    try:
        data = json.loads(body.decode('utf-8'))
        logger.info(f"Mensaje recibido: {data}")
        cam_id = data.get(DATA_CAMERA, "Desconocido")
        pool.apply_async(process_frame, args=(data,), callback=publish_detection_result)
        logger.info(f"Procesando mensaje para la cámara {cam_id}.")
    except Exception as e:
        logger.error(f"Error al procesar el mensaje de RabbitMQ: {e}")

def publish_detection_result(result):
    """
    Callback que publica el resultado del procesamiento mediante el publicador asíncrono.
    """
    if result is not None:
        logger.info(f"Publicando resultado: {result}")
        if publisher is not None:
            publisher.publish_async(result)
        else:
            logger.error("Publicador no disponible para publicar el resultado.")

def main():
    global pool, publisher

    try:
        mp.set_start_method("spawn", force=True)
        pool = Pool(processes=GPU_WORKERS, initializer=init_worker)
        publisher = ExamplePublisher(AMQP_URL)
        publisher.start()
        consumer = ReconnectingExampleConsumer(AMQP_URL, message_callback=rabbitmq_message_callback)
        logger.info("Iniciando consumer RabbitMQ...")
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado. Cerrando...")
    except Exception as e:
        logger.error(f"Error en main: {e}")
    finally:
        if publisher:
            publisher.stop()
        if pool:
            pool.close()
            pool.join()

if __name__ == "__main__":
    logger.info("Inicio de programa")
    main()
