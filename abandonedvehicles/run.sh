docker stop abandonedVehicles
docker rm abandonedVehicles

docker run  --rm \
-d  \
-v ./app:/app \
-v ./log:/log \
--network host \
--name abandonedVehicles  \
abandonedvehicles:202505
