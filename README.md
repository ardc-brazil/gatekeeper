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
    flask run -h localhost -p 8000
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

1. Map your new table in `app/models.py`
2. Run `flask db migrate -m "<comment>"`
3. Check the generated file under `migrations/versions/<generated_file>.py`
4. Run `flask upgrade`

