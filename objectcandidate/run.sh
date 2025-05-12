docker stop objectCandidate
docker rm objectCandidate

docker run  \
-d  \
-e TEST_MODE=true \
-v ./app:/app \
-v ./log:/log \
--network host \
--name objectCandidate  \
objectcandidate:202504
