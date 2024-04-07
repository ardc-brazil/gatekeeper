#!make

include dev.env
export $(shell sed 's/=.*//' dev.env)

# Reset
Color_Off=\033[0m       # Text Reset

# Regular Colors
Black=\033[0;30m        # Black
Red=\033[0;31m          # Red
Green=\033[0;32m        # Green
Yellow=\033[0;33m       # Yellow
Blue=\033[0;34m         # Blue
Purple=\033[0;35m       # Purple
Cyan=\033[0;36m         # Cyan
White=\033[0;37m        # White

# Background
On_Black=\033[40m       # Black
On_Red=\033[41m         # Red
On_Green=\033[42m       # Green
On_Yellow=\033[43m      # Yellow
On_Blue=\033[44m        # Blue
On_Purple=\033[45m      # Purple
On_Cyan=\033[46m        # Cyan
On_White=\033[47m       # White

# Docker commands
docker-build:
	time docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml build

docker-run:
	@echo "${On_Green}Starting docker containers${Color_Off}"
	time docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml up -d

docker-run-db:
	@echo "${On_Green}Starting docker containers${Color_Off}"
	time docker compose -f docker-compose-database.yaml up -d	

docker-stop:
	@echo "${On_Green}Stoping docker containers${Color_Off}"
	time docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml stop

docker-down:
	@echo "${On_Green}Downing docker containers${Color_Off}"
	time docker compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml down

docker-deployment: docker-build docker-stop docker-down docker-run
	

# Python commands
python-env:
	python3 -m venv venv
	. venv/bin/activate

python-pip-install:
	pip install -r requirements.txt

python-pip-freeze:
	pip freeze > requirements.txt

python-run:
	flask routes
	FLASK_ENV=development FLASK_DEBUG=1 flask run -h localhost -p 9092

# Database commands
db-upgrade:
	flask db upgrade

db-create-migration: # Usage: make MESSAGE="Add tenancy column to datasets" db-create-migration
	flask db migrate -m "$(MESSAGE)"

db-downgrade:
	flask db downgrade