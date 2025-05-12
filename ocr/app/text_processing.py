import re

class TextProcessor:
    ALFANUMERICO_REPLACEMENTS = {
        '0': 'O', '1': 'I', '2': 'Z', '3': 'B', '4': 'A', '5': 'S',
        '6': 'G', '7': 'T', '8': 'B', '9': 'P', 'c': 'C', 'f': 'F',
        'i': 'I', 'j': 'J', 'k': 'K', 'm': 'M', 'n': 'N', 'o': 'O',
        'p': 'P', 's': 'S', 't': 'T', 'u': 'U', 'v': 'V', 'w': 'W',
        'x': 'X', 'y': 'Y', 'z': 'Z'
    }

    ALFABETICO_REPLACEMENTS = {
        'c': 'C', 'f': 'F', 'h': 'H', 'i': '1', 'j': 'J', 'k': 'K',
        'l': '1', 'm': 'M', 'n': 'N', 'p': 'P', 'u': 'U', 'v': 'V',
        'w': 'W', 'x': 'X', 'y': 'Y', "a": "0", "b": "0", "d": "0",
        "e": "0", "g": '9', 'o': '0', 'q': '9', 's': 'S', 't': '7',
        'z': '2'
    }

    NUMERICO_REPLACEMENTS = {
        'O': '0', 'o': '0', 'I': '1', 'i': '1', 'Z': '2', 'z': '2',
        'G': '6', 'g': '9', 'T': '7', 't': '7', 'B': '8', 'b': '0',
        'u': '0', 'P': '9', 'p': '9', 'q': '9', 'D': '0', 'd': '0',
        'S': '5', 's': '5', 'l': '1', 'L': '1', 'a': '0', 'Q': '0',
        'C': '0', 'c': '0'
    }

    @staticmethod
    def clean_plate(plate_text):
        """Remove non-alphanumeric characters and hyphens."""
        plate_text = re.sub(r'[^A-Za-z0-9]+', '', plate_text)
        status = 1 if bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9]{2}[0-9]{3}', plate_text)) else 2
        return plate_text, status

    @staticmethod
    def process_light_vehicle_plate(plate_text):
        """Process license plates for light vehicles."""
        corrected_plate = list(plate_text)

        if corrected_plate[0].isdigit() or corrected_plate[0].islower():
            corrected_plate[0] = TextProcessor.ALFABETICO_REPLACEMENTS.get(
                corrected_plate[0], corrected_plate[0].upper()
            )

        for i in range(1, 3):
            if corrected_plate[i].islower():
                corrected_plate[i] = TextProcessor.ALFANUMERICO_REPLACEMENTS.get(
                    corrected_plate[i], corrected_plate[i].upper()
                )

        for i in range(4, len(plate_text)):
            if not corrected_plate[i].isdigit():
                corrected_plate[i] = TextProcessor.NUMERICO_REPLACEMENTS.get(
                    corrected_plate[i], '0'
                )

        plate_str = ''.join(corrected_plate)
        if re.match(r'^[A-Z][A-Z0-9][A-Z0-9]-\d{3}$', plate_str):
            return plate_str
        return plate_text

    @staticmethod
    def process_minor_vehicle_plate(plate_text):
        """Process license plates for minor vehicles."""
        corrected_plate = list(plate_text)

        if corrected_plate[0].isdigit() or corrected_plate[0].islower():
            corrected_plate[0] = TextProcessor.ALFANUMERICO_REPLACEMENTS.get(
                corrected_plate[0], corrected_plate[0].upper()
            )

        if corrected_plate[1].islower():
            corrected_plate[1] = TextProcessor.ALFABETICO_REPLACEMENTS.get(
                corrected_plate[1], corrected_plate[1].upper()
            )
        
        for i in range(3, len(plate_text)):
            if not corrected_plate[i].isdigit():
                corrected_plate[i] = TextProcessor.NUMERICO_REPLACEMENTS.get(
                    corrected_plate[i], '0'
                )
                
        plate_str = ''.join(corrected_plate)
        if re.match(r'^[A-Z0-9][A-Z]-\d{4}$', plate_str):
            return plate_str
        return plate_text