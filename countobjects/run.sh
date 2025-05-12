docker stop countObjects
docker rm countObjects

docker run  \
--restart=always \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name countObjects  \
countobjects:202505