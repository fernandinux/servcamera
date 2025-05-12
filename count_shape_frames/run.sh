docker stop countshpe
docker rm countshpe

docker run  \
-d  \
-e TEST_MODE=true \
-v ./app:/app \
-v ./log:/log \
--network host \
--name countshpe  \
objectcandidate:202504
