# docker stop objectDetector
# docker rm objectDetector

# docker run  \
# -d  \
# -e TEST_MODE=false \
# -v ./app:/app \
# -v ./log:/log \
# --network host \
# --name objectDetector  \
# --gpus all  \
# objectdetector:202504

###### Crea 3 contenedores de una ###########
#for i in $(seq 1 3); do
#  name="objectDetector$i"
#
#  # Solo el primero monta ./log:/log
#  if [ "$i" -eq 1 ]; then
#    docker stop "$name"
#    docker rm "$name"
#
#    docker run -d \
#      -v ./app:/app \
#      -v ./log:/log \
#      --network host \
#      --name "$name" \
#      --gpus all \
#      objectdetector:202504
#  else
#    docker stop "$name"
#    docker rm "$name"
#
#    docker run -d \
#      -v ./app:/app \
#      --network host \
#      --name "$name" \
#      --gpus all \
#      objectdetector:202504
#  fi
#done


######################################

######### Agrega 1 contenedor ########

docker run -d \
  -v ./app:/app \
  --network host \
  --name "objectDetector4" \
  --gpus all \
  objectdetector:202504
#####################################
