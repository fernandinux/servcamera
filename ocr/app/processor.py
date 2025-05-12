import time
import logging
from text_processing import TextProcessor
from config import *
import numpy as np # type: ignore

logger = logging.getLogger(NAME_LOGS)

def getOCR(model_ocr, img, mode  = True):
    init_time = time.time()
    text, conf = perform_ocr(model_ocr, img)
    logger.debug(f"      Tiempo de PaddleOcr:           {time.time()-init_time}")
    if text:
        init_time = time.time()
        text, conf, status = validate_and_clean_plate((text, conf)) 
        logger.debug(f"      Tiempo de Reg Exp:             {time.time()-init_time}")
        return text, int(conf*100) if conf else 0, status
    return 'YOLO' if mode else '', 0, 2 

def perform_ocr(ocr_model, image):
    """Perform OCR on plate image."""
    try:
        result = ocr_model.ocr(image, cls=CLS_OCR_FLAG)[0]
        if result is None: return None, None
        
        res = result[0][1] #(text,conf)
        if not res:return None, None

        return res[0], res[1]
    
    except Exception as e:
        logging.error(f"OCR error: {str(e)}")
    return None, None

def validate_and_clean_plate(ocr_result):
    """Validate and clean plate text."""
    text, confidence = ocr_result
    if not text:
        return '', 0, 2 
    cleaned_text, status = TextProcessor.clean_plate(text)
    # if not 3 <= len(cleaned_text) <= 7:
    #     return '', 0
    # hyphen_pos = cleaned_text.find('-')
    # if hyphen_pos == 2:
    #     plate = TextProcessor.process_minor_vehicle_plate(cleaned_text)
    #     return plate, confidence
    # elif hyphen_pos == 3:
    #     return TextProcessor.process_light_vehicle_plate(cleaned_text), confidence
    return cleaned_text, confidence, status