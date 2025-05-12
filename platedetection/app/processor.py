import time
import logging
from config import *
import numpy as np # type: ignore

logger = logging.getLogger(NAME_LOGS)

def getPlate(model_plate, img):
    return  model_plate.predict(source = img, conf = CONF, verbose = False)

def getPlateImage(box, img, pad = 0):
    x1, y1, x2, y2 = map(int, box.xyxy[0])

    if pad == 0:
        plate_cut = img[y1:y2, x1:x2]
    else:
        x1 = max(0, int(x1 + x1 * pad))
        x2 = min(img.shape[1], int(x2 - x2 * pad))
        y1 = max(0, int(y1 + y1 * pad))
        y2 = min(img.shape[0], int(y2 - y2 * pad))
        
        # Extract and process plate region
        plate_cut = img[y1:y2, x1:x2]

    return plate_cut, [x1, y1, x2, y2], True

def process_plate(model_plate = None, img = None):
    init_time = time.time()
    results = getPlate(model_plate, img)
    logger.debug(f"      Tiempo YOLO:                   {time.time()-init_time}")
    for result in results:
        for box in result.boxes: 
            return getPlateImage(box, img)
    return None, None, False


