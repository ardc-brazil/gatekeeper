import uvicorn

# import os 
# print(os.getcwd())

# from flask import Flask
# from flask_migrate import Migrate
# from flask_sqlalchemy import SQLAlchemy
from fastapi import FastAPI

from exception.UnauthorizedException import UnauthorizedException
from exception.NotFoundException import NotFoundException
from exception.ConflictException import ConflictException
from controller.interceptor.exception_handler import conflict_exception_handler, not_found_exception_handler, unauthorized_exception_handler
from container import Container

# from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
# from casbin import SyncedEnforcer
# from app.controllers.interceptors.authorization_container import AuthorizationContainer
# from postgresql_watcher import PostgresqlWatcher

from controller.v1.client.client import router as client_router
from controller.v1.infrastructure.infrastructure import router as infrastructure_router
from controller.v1.tenancy.tenancy import router as tenancies_router

# db = SQLAlchemy()

# def create_app() -> FastAPI:
# app = Flask(__name__)
container = Container()

db = container.db()
db.create_database()

app = FastAPI(
    title="Gatekeeper API",
    description="Gatekeeper API is the main backend for DataMap",
    version="0.0.1",
    redirect_slashes=True,
    root_path="/api",
)

app.container = container

# Load app configuration
# app.config.from_prefixed_env("GATEKEEPER")

# Casbin config
# casbin_adapter = CasbinSQLAlchemyAdapter(app.config["CASBIN_DATABASE_URL"])
# enforcer = SyncedEnforcer("app/resources/casbin_model.conf", casbin_adapter)
# enforcer.enable_auto_build_role_links(True)
# enforcer.start_auto_load_policy(5)  # reload policy every 5 seconds
# watcher = PostgresqlWatcher(
#     host=app.config["DB_HOST"],
#     user=app.config["DB_USER"],
#     password=app.config["DB_PASSWORD"],
#     port=app.config["DB_PORT"],
#     dbname=app.config["DB_NAME"],
# )
# watcher.set_update_callback(enforcer.load_policy)
# enforcer.set_watcher(watcher)
# AuthorizationContainer.instance(app, enforcer, casbin_adapter)

# API routes
app.include_router(client_router, prefix="/v1")
app.include_router(infrastructure_router, prefix="/v1")
app.include_router(tenancies_router, prefix="/v1")

app.add_exception_handler(ConflictException, conflict_exception_handler)
app.add_exception_handler(NotFoundException, not_found_exception_handler)
app.add_exception_handler(UnauthorizedException, unauthorized_exception_handler)

# Migrate(app, db)

# db.init_app(app)

# remove trailing slash in the api
# app.url_map.strict_slashes = False

# from app.controllers.v1 import api

# app.register_blueprint(api)

############################################################
# To create a new version of the API, follow this pattern
############################################################
# from app.controllers.v2 import api
# app.register_blueprint(api)

# return app

# app = create_app()

if __name__ == "__main__":
    # app.run(host="localhost", port=9092)
    uvicorn.run(
        app,
        host="localhost",
        port=9092,
    )
