from flask import Flask
from flask_migrate import Migrate
import flask_restx
from flask_sqlalchemy import SQLAlchemy
from casbin_sqlalchemy_adapter import Adapter as SQLAlchemyAdapter
from casbin import Enforcer

from app.controllers.interceptors.authorization import authorization_middleware

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

    adapter = SQLAlchemyAdapter(db)
    enforcer = Enforcer('app/resources/casbin_policy.conf', adapter)
    enforcer.load_policy()

    app.wsgi_app = authorization_middleware(enforcer)(app.wsgi_app)

    return app
