# Gatekeeper

Backend for DataAmazon.

## Prerequisites

- Docker
- Docker Compose

## Environment Setup

1. Start docker containers

    ```
    docker-compose up -d
    ```

2. Access pgAdmin in your browser at `http://localhost:5050` to configure the connection to PostgreSQL
    - Log in using the admin credentials defined in `docker-compose.yml` file, under the service `gatekeeper-pgadmin`.
    - Right-click on "Servers" and select "Create" -> "Server".
    - In the "General" tab, give the server a name (e.g., "Gatekeeper DB").
    - In the "Connection" tab, fill in the following fields:
        - Hostname/address: gatekeeper-db
        - Port: 5432
        - Maintenance database: gatekeeper_db
        - Username: gk_admin
        - Password: check in `docker-compose.yml`
    - Click "Save" to add the server.

3. Create a virtual environment and activate it

    ```
    python3 -m venv venv
    source venv/bin/activate
    ```

4. Install project dependencies

    ```
    pip install -r requirements.txt
    ```

5. Run database migrations

    ```
    flask db upgrade
    ```

6. Start the application by using any of the following

    ```
    python app.py
    ```

    ```
    flask run -h localhost -p 8080
    ```

7. If you need to delete the docker containers

    ```
    docker-compose down
    ```

    Obs.: this will delete the containers, but not the images generated nor the database data, since it uses a docker volume to persistently storage data.

### Running tests

Run `pytest`. This will execute all unit tests within `./tests` with the prefix `test_*.py`.

### Creating new migrations

To create new migrations, follow the steps below.

1. Map your new table in a new file in `models/{your_new_model}.py`
2. Import your model in `app/__init__.py`, before the migrate config
3. Run `flask db migrate -m "<comment>"`
4. Check the generated file under `migrations/versions/<generated_file>.py`
5. Run `flask db upgrade`

### Deploying

1. `ssh -i ~/.ssh/data-amazon-key-pair.pem ec2-user@ec2-34-194-118-180.compute-1.amazonaws.com`
2. `cd gatekeeper`
3. `git pull`
4. `docker build -t gatekeeper .`
5. `docker compose -f docker-compose-infrastructure.yaml down`
6. `docker compose -f docker-compose-infrastructure.yaml up -d`

### Accessing the application in prod

* For the application: `curl -X GET http://ec2-34-194-118-180.compute-1.amazonaws.com/api/`
* For pgAdmin: Access `http://ec2-34-194-118-180.compute-1.amazonaws.com/` in the browser.

### Create a new API Key and Secret in local development

1. `curl -X POST http://localhost:8080/api/clients/ -H 'Content-Type: application/json' -H "X-Admin-Secret: {shared-password}" -d '{"name": "DataAmazon BFF", "secret": "{api-password}"}'``
2. `curl -X GET -H "X-Api-Key: {generated-api-key}" -H "X-Api-Secret: {defined-api-secret}" localhost:8080/api/datasets/`