import face_recognition
import time
import numpy as np

# Load the jpg files into numpy arrays
tiempo_open_img = []
inicio_tiempo = time.time()
biden_image = face_recognition.load_image_file("biden.jpg")
tiempo_open_img.append(time.time() - inicio_tiempo)
inicio_tiempo = time.time()
obama_image = face_recognition.load_image_file("obama.jpg")
tiempo_open_img.append(time.time() - inicio_tiempo)
inicio_tiempo = time.time()
unknown_image = face_recognition.load_image_file("obama2.jpg")
tiempo_open_img.append(time.time() - inicio_tiempo)
print(f"Tiempo promedio de lectura: {np.mean(tiempo_open_img)}")

# Get the face encodings for each face in each image file
# Since there could be more than one face in each image, it returns a list of encodings.
# But since I know each image only has one face, I only care about the first encoding in each image, so I grab index 0.
try:
    tiempo_encoding = []
    biden_face_encoding = face_recognition.face_encodings(biden_image)[0]
    tiempo_encoding.append(time.time() - inicio_tiempo)
    inicio_tiempo = time.time()
    obama_face_encoding = face_recognition.face_encodings(obama_image)[0]
    tiempo_encoding.append(time.time() - inicio_tiempo)
    inicio_tiempo = time.time()
    unknown_face_encoding = face_recognition.face_encodings(unknown_image)[0]
    tiempo_encoding.append(time.time() - inicio_tiempo)
    inicio_tiempo = time.time()
    print(f"Tiempo promedio de encoding: {np.mean(tiempo_encoding)}")
    
except IndexError:
    print("I wasn't able to locate any faces in at least one of the images. Check the image files. Aborting...")
    quit()

known_faces = [
    biden_face_encoding,
    obama_face_encoding
]

# results is an array of True/False telling if the unknown face matched anyone in the known_faces array
inicio_tiempo = time.time()
results = face_recognition.compare_faces(known_faces, unknown_face_encoding)
elapsed_time = time.time() - inicio_tiempo
print(f"Tiempo de comparacion: {elapsed_time}")

print("Is the unknown face a picture of Biden? {}".format(results[0]))
print("Is the unknown face a picture of Obama? {}".format(results[1]))
print("Is the unknown face a new person that we've never seen before? {}".format(not True in results))
