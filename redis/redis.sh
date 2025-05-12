docker stop redis
docker rm redis

docker run \
  --restart=always \
  -d \
  --network host \
  --name redis \
  -v $(pwd)/data:/data \
  redis:alpine \
  redis-server --save 900 1 --appendonly yes
