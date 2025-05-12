# docker stop ocr
# docker rm ocr

# docker run  \
# -d  \
# -v ./app:/app \
# -v ./log:/log \
# -v /mnt/camaras/cameradata:/output \
# --network host \
# --name ocr  \
# --gpus all  \
# ocr:202504

for i in $(seq 1 4); do
  name="ocr$i"

  # Solo el primero monta ./log:/log
  if [ "$i" -eq 1 ]; then
    docker stop "$name"
    docker rm "$name"

    docker run -d \
      -v ./app:/app \
      -v ./log:/log \
      --network host \
      --name "$name" \
      --gpus all \
      ocr:202504
  else
    docker stop "$name"
    docker rm "$name"
    
    docker run -d \
      -v ./app:/app \
      --network host \
      --name "$name" \
      --gpus all \
      ocr:202504
  fi
done
