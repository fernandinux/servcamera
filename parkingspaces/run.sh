docker stop parkingSpaces
docker rm parkingSpaces

docker run  \
--restart=always \
-d  \
-v ./app:/app \
-v ./log:/log \
-v ./output:/output \
--network host \
--name parkingSpaces  \
parkingspaces:202505