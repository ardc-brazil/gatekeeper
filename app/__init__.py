from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config')
    app.config.from_envvar('APP_CONFIG_FILE', silent=True)

    migrate = Migrate(app, db)

    db.init_app(app)

    from app.routes import bp
    app.register_blueprint(bp)

    return app
