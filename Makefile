#!make

include ${ENV_FILE_PATH}
export $(shell sed 's/=.*//' ${ENV_FILE_PATH})

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
	time docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml build

docker-run:
	@echo "${On_Green}Starting docker containers${Color_Off}"
	time docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml up -d

docker-run-db:
	@echo "${On_Green}Starting docker containers${Color_Off}"
	time docker-compose -f docker-compose-database.yaml up -d	

docker-stop:
	@echo "${On_Green}Stoping docker containers${Color_Off}"
	time docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml stop

docker-down:
	@echo "${On_Green}Downing docker containers${Color_Off}"
	time docker-compose -f docker-compose-infrastructure.yaml -f docker-compose-database.yaml down

docker-prune:
	@echo "${On_Green}Images prune${Color_Off}"
	time docker image prune -a -f

docker-deployment: docker-build docker-stop docker-down docker-run docker-prune

docker-deployment-no-prune: docker-build docker-stop docker-down docker-run
	
# Python commands
python-env:
	@echo "${On_White}\rAtention!${Color_Off}"
	@echo "Use vscode and create the environment locall to run the application"
	@echo "Check more about it on https://code.visualstudio.com/docs/python/environments#_creating-environments"

python-pip-install:
	pip3 install -r requirements.txt

python-pip-freeze:
	pip3 freeze > requirements.txt

python-run:
	uvicorn app.main:fastAPIApp --host 0.0.0.0 --port 9092 --reload

# Database commands
db-upgrade:
	python3 -m alembic upgrade head

db-create-migration: # Usage: make MESSAGE="Add tenancy column to datasets" db-create-migration
	python3 -m alembic revision --autogenerate -m "$(MESSAGE)"

db-downgrade:
	python3 -m alembic downgrade -1

# Integration Test commands
integration-test-build:
	@echo "${On_Green}Building integration test containers${Color_Off}"
	docker-compose -f docker-compose-integration-test.yaml build

integration-test-up:
	@echo "${On_Green}Starting integration test containers${Color_Off}"
	docker-compose -f docker-compose-integration-test.yaml up -d
	@echo "Waiting for services to be ready..."
	@timeout 60 bash -c 'until curl -s http://localhost:9094/api/v1/health-check/ > /dev/null; do sleep 2; done' || echo "Gatekeeper may not be ready"
	@timeout 30 bash -c 'until curl -s http://localhost:8083/__admin/health > /dev/null; do sleep 1; done' || echo "WireMock may not be ready"
	@echo "${On_Green}Integration test containers ready${Color_Off}"
	@echo "Services available:"
	@echo "  - Gatekeeper API: http://localhost:9094"
	@echo "  - WireMock (DOI): http://localhost:8083"
	@echo "  - MinIO Console: http://localhost:9003"
	@echo "  - MinIO API: http://localhost:9002"
	@echo "  - PostgreSQL: localhost:5433"
	@echo "  - PGAdmin: http://localhost:5051"
	@echo "  - TUSd: http://localhost:1081"

integration-test-down: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-down
	@echo "${On_Green}Stopping integration test containers${Color_Off}"
	docker-compose -f docker-compose-integration-test.yaml down
	@echo "${On_Green}Integration test containers stopped${Color_Off}"

integration-test-clean: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-clean
	@echo "${On_Green}Cleaning integration test containers and volumes${Color_Off}"
	docker-compose -f docker-compose-integration-test.yaml down -v
	@echo "${On_Green}Integration test containers and volumes cleaned${Color_Off}"

integration-test-logs: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-logs
	@echo "${On_Green}Showing integration test container logs${Color_Off}"
	docker-compose -f docker-compose-integration-test.yaml logs --tail=50

integration-test-restart: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-restart
	@$(MAKE) ENV_FILE_PATH=$(ENV_FILE_PATH) integration-test-down
	@$(MAKE) ENV_FILE_PATH=$(ENV_FILE_PATH) integration-test-up

integration-test-run: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-run
	@echo "${On_Green}Running integration tests${Color_Off}"
	pytest tests/integration/ -v

integration-test-run-specific: # Usage: make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_dataset_snapshot.py integration-test-run-specific
	@echo "${On_Green}Running specific integration test: ${TEST_PATH}${Color_Off}"
	pytest ${TEST_PATH} -v

# Complete integration test workflow
integration-test-full: # Usage: make ENV_FILE_PATH=integration-test.env integration-test-full
	@echo "${On_Green}Running complete integration test workflow${Color_Off}"
	@$(MAKE) ENV_FILE_PATH=$(ENV_FILE_PATH) integration-test-up
	@echo "Running database migrations inside container..."
	@docker exec datamap_gatekeeper_test_integration python3 -m alembic upgrade head || echo "Migration may have failed - continuing with tests"
	@echo "Seeding test data..."
	@docker exec datamap_postgres_test_integration psql -U gk_admin -d gatekeeper_db -f /tmp/seed_clients.sql || echo "Seed may have failed - continuing with tests"
	@echo "Running integration tests..."
	@$(MAKE) ENV_FILE_PATH=$(ENV_FILE_PATH) integration-test-run
	@$(MAKE) integration-test-down
