docker stop restrictedarea
docker rm restrictedarea

docker run \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name restrictedArea  \
restrictedarea:202505
