# from flask import Flask
# from flask_migrate import Migrate
# import flask_restx
# from flask_sqlalchemy import SQLAlchemy
from fastapi import FastAPI
from app.config.container import Container
import app.controllers.v1.infrastructure.infrastructure as infrastructure
from app.controllers.v1.router import v1_base_router
# from config.container import Container

# db = SQLAlchemy()

def create_app():
    # app = Flask(__name__)
    container = Container()

    app = FastAPI()
    app.container = container
    v1_base_router.include_router(infrastructure.router)
    app.include_router(v1_base_router)

    # app.config.from_object('config')
    # app.config.from_envvar('APP_CONFIG_FILE', silent=True)

    # from app.models.datasets import Datasets
    # from app.models.users import Users
    # migrate = Migrate(app, db)

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

    return app
