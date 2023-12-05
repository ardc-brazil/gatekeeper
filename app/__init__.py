from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from casbin.persist.adapters import FileAdapter
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from casbin import Enforcer
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from app.controllers.interceptors.authorizar_container import AuthorizerContainer
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config')
    app.config.from_envvar('APP_CONFIG_FILE', silent=True)

    # Casbin config
    casbin_adapter = CasbinSQLAlchemyAdapter(os.environ['CASBIN_DATABASE_URL'])
    enforcer = Enforcer('app/resources/casbin_model.conf', casbin_adapter)
    enforcer.enable_auto_build_role_links(True)
    AuthorizerContainer.instance(app, enforcer, casbin_adapter)

    # Models config
    from app.models.datasets import Datasets
    from app.models.users import Users
    migrate = Migrate(app, db)

    db.init_app(app)

    # remove trailing slash in the api
    app.url_map.strict_slashes = False

    from app.controllers.v1 import api 
    app.register_blueprint(api)

    ############################################################
    # To create a new version of the API, follow this pattern
    ############################################################
    # from app.controllers.v2 import api 
    # app.register_blueprint(api)

    return app
