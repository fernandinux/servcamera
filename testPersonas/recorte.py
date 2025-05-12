import os
import cv2
from ultralytics import YOLO

# Configuración de carpetas
input_folder = './'      # Carpeta con las imágenes de entrada
output_folder = './crop'         # Carpeta donde se guardarán los recortes


# Crear la carpeta de salida si no existe
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Cargar el modelo YOLOv8 para detección (usamos un modelo preentrenado)
model = YOLO("yolov8n.pt")  # Asegúrate de tener el archivo o descargarlo

# Recorrer cada imagen en la carpeta de entrada
for filename in os.listdir(input_folder):
    if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        image_path = os.path.join(input_folder, filename)
        image = cv2.imread(image_path)
        if image is None:
            print(f"Error al cargar la imagen {image_path}")
            continue

        # Ejecutar el modelo para obtener resultados
        results = model(image)
        person_count = 0  # contador de personas detectadas en la imagen

        # Iterar sobre los resultados
        for result in results:
            # Iterar sobre cada detección
            for bbox, cls in zip(result.boxes.xyxy, result.boxes.cls):
                # Filtrar detecciones de la clase 'persona' (class id 0 en COCO)
                if int(cls) == 0:
                    x1, y1, x2, y2 = map(int, bbox[:4])
                    # Recortar la imagen a partir del bounding box
                    crop = image[y1:y2, x1:x2]
                    # Guardar la imagen recortada en la carpeta de salida
                    output_filename = f"{os.path.splitext(filename)[0]}_person{person_count}.jpg"
                    output_path = os.path.join(output_folder, output_filename)
                    cv2.imwrite(output_path, crop)
                    person_count += 1

        print(f"{filename}: se detectaron y guardaron {person_count} persona(s).")
