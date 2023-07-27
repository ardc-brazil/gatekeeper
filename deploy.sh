#!/bin/bash
GREEN='\033[0;32m'
NC='\033[0m'
echo -e "${GREEN}[----- Cloning Gatekeeper -----]${NC}"
rm -rf gatekeeper/
git clone https://{access_token}@github.com/ardc-brazil/gatekeeper.git
cd gatekeeper
echo -e "${GREEN}[----- Stopping docker instances -----]${NC}"
docker compose down
echo -e "${GREEN}[----- Starting docker instances -----]${NC}"
docker compose up -d
echo -e "${GREEN}[----- Configuring repository -----]${NC}"
python3.8 -m venv venv
source venv/bin/activate
./venv/bin/python3.8 -m pip install -r requirements.txt
echo -e "${GREEN}[----- Executing database migration -----]${NC}"
./venv/bin/python3.8 -m flask db upgrade
echo -e "${GREEN}[----- Generating distributables -----]${NC}"
./venv/bin/python3.8 -m pip install build
./venv/bin/python3.8 -m build --wheel
./venv/bin/python3.8 -m pip install dist/gatekeeper-1.0.0-py3-none-any.whl
./venv/bin/python3.8 -m pip install gunicorn
if [ ! -f ./gunicorn.pid ]; then
    echo -e "${GREEN}[----- Shutdown old instances -----]${NC}"
    kill -9 `cat ../gunicorn.pid` > /dev/null 2> /dev/null || :
    echo -e "${GREEN}[----- Waiting termination of old instances -----]${NC}"
    tail --pid=`cat ../gunicorn.pid` -f /dev/null
    sleep 10
    rm ../gunicorn.pid
else
    echo -e "${GREEN}[----- No old instances running -----]${NC}"
fi
echo -e "${GREEN}[----- Starting server -----]${NC}"
./venv/bin/python3.8 -m gunicorn -w 2 -b 0.0.0.0:8080 'app:create_app()' --daemon --pid ../gunicorn.pid --error-logfile ../gunicorn_error.log
echo -e "${GREEN}[----- Server deployed at port 8080 -----]${NC}"