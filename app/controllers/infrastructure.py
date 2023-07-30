from flask import Blueprint

infrastructure_bp = Blueprint('infra', __name__, url_prefix='/infra')

@infrastructure_bp.get('/health-check')
def flask_health_check():
	return "success"