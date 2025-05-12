docker stop averageSpeed
docker rm averageSpeed

docker run  \
--restart=always \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name averageSpeed  \
averagespeed:202505