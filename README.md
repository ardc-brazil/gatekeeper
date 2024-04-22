# Gatekeeper

Backend for DataAmazon.

## Prerequisites

- Docker
- Docker Compose

## Environment Setup

**Use Makefile targets to make your life easier!**

1. Start docker containers

```sh
make ENV={env} docker-run
```

2. Access pgAdmin in your browser at <http://localhost:5050> or <http://localhost/pgadmin> to use PgAdmin to connect to
the PostgreSQL database

- Log in using the admin credentials defined in `docker-compose.yml` file, under the service `gatekeeper-pgadmin`.
- Double click in `Servers > Gatekeeper DB` and inform the password from `docker-compose.yml`

3. Create a virtual environment and activate it

```sh
make ENV={env} python-env
```

4. Install project dependencies

> If your are running MacOS, install openssl first:
> `brew install openssl`

```sh
make ENV={env} python-pip-install
```

5. Run database migrations

```sh
make ENV={env} db-migration
```

6. Start the application by using any of the following

```sh
make ENV={env} python-run
```

7. If you need to delete the docker containers

```sh
make ENV={env} docker-down
```

Obs.: this will delete the containers, but not the images generated nor the database data, since it uses a docker 
volume to persistently storage data.

### Running tests

Run `pytest`. This will execute all unit tests within `./tests` with the prefix `test_*.py`.

### Creating new migrations

To create new migrations, follow the steps below.

1. Map your new table in a new file in `models/{your_new_model}.py`
2. Import your model in `app/__init__.py`, before the migrate config
3. Run `make ENV={env} db-create-migration "{COMMENT}"`
4. Check the generated file under `migrations/versions/<generated_file>.py` and see if any fix is needed.
5. Run `make ENV={env} db-upgrade`
6. Check the database, if there's any problem, run `make ENV={env} db-downgrade`

> **WARNING**: Sometimes a new migration tries to delete the `casbin_rule` table. This is not intended and should be investigated. As of now, check the migration file to see if the upgrade and downgrade has a create and/or delete table for `cabin_rule`. If, so, just delete this statement from the files (from both upgrade and downgrade).

### Deploying

> **WARNING:** The current deployment process causes downtime for services.

```sh
# Connect to USP infra
ssh datamap@143.107.102.162 -p 5010

# Navegate to the project folder
cd gatekeeper

# Get the last (main) branch version
git pull

# Start python virtual env
python3 -m venv venv
. venv/bin/activate

# Install libraries
make ENV={env} python-pip-install

# Run db migrations
make ENV={env} db-upgrade

# Deactivate python virtual env
deactivate

# Refresh and deploy the last docker image.
make docker-deployment
```

### Accessing the application in prod

* Frontend: `https://datamap.pcs.usp.br/`
* Backend: `https://datamap.pcs.usp.br/api/v1/docs`
* pgAdmin: `http://datamap.pcs.usp.br/pgadmin`
* MIN.io: `https://datamap.pcs.usp.br/minio/ui/`
* TUSd: `https://datamap.pcs.usp.br/files/`

# First Setup for Local Development

## Create a new API Key and Secret in local development

1. For the first client, the easiest way is to remove the `authorize` interceptor from the client creation endpoint
2. Create with `curl -X POST http://localhost:9092/api/v1/clients -H 'Content-Type: application/json' -d '{"name": "DataAmazon Local Client", "secret": "{secret}"}'`
3. Test with `curl -X GET -H "X-Api-Key: {generated-api-key}" -H "X-Api-Secret: {defined-api-secret}" localhost:9092/api/v1/datasets`

## Dataset import

1. Change the database host, api key and api secret in `tools/import_dataset.py`
2. Remove the authorization interceptor for the dataset creation route
3. `python tools/import_dataset.py`

## User Creation

1. Open `http://localhost:9092/api/v1/docs` in the browser
2. Under the "Authorize" button (top right corner), paste the api key and secret
3. Execute the POST for users route and create a new user

## Role management

1. Open the pgAdmin at `http://localhost:9092/pgadmin` and login
2. Execute SQL in `app/resources/casbin_seed_policies.sql` and `app/resources/tenancy_seed.sql` in the gatekeeper database
3. Add your own user to the admin role, so you can test everything:

```
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', '{used_id}', 'admin', NULL, NULL, NULL, NULL);
```

### Issues

1. If you have the psycopg_2 problem, run `brew install postgresql`
2. If you have the "Failed to build dependency-injector", use Python 3.10.4
