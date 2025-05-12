docker stop trafficCongestion
docker rm trafficCongestion

docker run  \
--restart=always \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name trafficCongestion \
trafficcongestion:202505