# Docker commands
docker-build:
	docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml build

docker-run:
	docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml up -d

docker-stop:
	docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml stop

docker-down:
	docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml down

docker-deployment:
	docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml down

# Python commands
python-env:
	python3 -m venv venv
	source venv/bin/activate

python-pip-install:
	pip install -r requirements.txt

python-run:
	flask run -h localhost -p 8080

# Database commands
db-migration:
	flask db upgrade
