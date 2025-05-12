docker stop listComparator
docker rm listComparator

docker run  --rm \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name listComparator  \
listcomparator:202505
