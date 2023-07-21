from flask import Blueprint

bp = Blueprint('routes', __name__, url_prefix='/api')
from app.controllers.datasets import datasets_bp
bp.register_blueprint(datasets_bp)
