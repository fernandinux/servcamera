docker stop colorAttribute
docker rm colorAttribute

docker run  \
--restart=always \
-d  \
-v ./app:/app \
-v ./log:/log \
-v /mnt/camaras/cameradata:/output \
--network host \
--name colorAttribute  \
color:202504
