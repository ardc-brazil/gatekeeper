#!/bin/bash
rm -rf gatekeeper/
git clone https://{access_token}@github.com/ardc-brazil/gatekeeper.git
cd gatekeeper
docker compose down
docker compose up -d
python3.8 -m venv venv
source venv/bin/activate
./venv/bin/python3.8 -m pip install -r requirements.txt
./venv/bin/python3.8 -m flask db upgrade
./venv/bin/python3.8 -m pip install build
./venv/bin/python3.8 -m build --wheel
./venv/bin/python3.8 -m pip install dist/gatekeeper-1.0.0-py3-none-any.whl
./venv/bin/python3.8 -m pip install gunicorn
./venv/bin/python3.8 -m gunicorn -w 4 -b 0.0.0.0:8080 'app:create_app()'