from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from casbin import SyncedEnforcer
from app.controllers.interceptors.authorization_container import AuthorizationContainer
from postgresql_watcher import PostgresqlWatcher

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)

    # Load app configuration
    app.config.from_prefixed_env("GATEKEEPER")

    # Casbin config
    casbin_adapter = CasbinSQLAlchemyAdapter(app.config["CASBIN_DATABASE_URL"])
    enforcer = SyncedEnforcer("app/resources/casbin_model.conf", casbin_adapter)
    enforcer.enable_auto_build_role_links(True)
    enforcer.start_auto_load_policy(5)  # reload policy every 5 seconds
    enforcer.set_watcher
    watcher = PostgresqlWatcher(
        host=app.config["DB_HOST"],
        user=app.config["DB_USER"],
        password=app.config["DB_PASSWORD"],
        port=app.config["DB_PORT"],
        dbname=app.config["DB_NAME"],
    )
    watcher.set_update_callback(enforcer.load_policy)
    enforcer.set_watcher(watcher)
    AuthorizationContainer.instance(app, enforcer, casbin_adapter)

    Migrate(app, db)

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
