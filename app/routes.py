from flask import Blueprint

root = Blueprint('routes', __name__, url_prefix='/api')
# from app.controllers.datasets import datasets_bp
# root.register_blueprint(datasets_bp)
from app.controllers.infrastructure import infrastructure_bp
root.register_blueprint(infrastructure_bp)
from app.controllers.v1.clients import clients_bp
root.register_blueprint(clients_bp)
