docker stop roadAccident
docker rm roadAccident

# -v /SSD500/mvp/project2/app/output/images/25/2025-11-02/21/frames:/app/frames \

docker run  \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name roadAccident  \
--gpus all  \
roadaccident:202505
