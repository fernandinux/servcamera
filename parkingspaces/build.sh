
TAGNAME=$(basename "$PWD"):$(date +'%Y%m')
docker rmi $TAGNAME
docker build -t $TAGNAME .

