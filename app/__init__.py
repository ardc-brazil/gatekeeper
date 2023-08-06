from flask import Flask
from flask_migrate import Migrate
import flask_restx
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config')
    app.config.from_envvar('APP_CONFIG_FILE', silent=True)

    from app.models.datasets import Datasets
    migrate = Migrate(app, db)

    db.init_app(app)

    from app.controllers.v1 import api 
    app.register_blueprint(api)

    ############################################################
    # To create a new version of the API, follow this pattern
    ############################################################
    # from app.controllers.v2 import api 
    # app.register_blueprint(api)

    return app
