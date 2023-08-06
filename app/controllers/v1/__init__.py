from flask import Blueprint
from flask_restx import Api
from app.controllers.v1.datasets import namespace as datasets_ns
# from app.controllers.v1.clients import namespace as clients_ns
from app.controllers.v1.datasets_search import namespace as datasets_search_ns
from app.controllers.v1.datasets_filters import namespace as datasets_filters_ns
from app.controllers.v1.infrastructure import namespace as healthcheck_ns

api = Blueprint('apiv1', __name__, url_prefix='/api/v1')

authorizations = {
    'api_key': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Api-Key'
    },
    'api_secret': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Api-Secret'
    },
    'api_admin_key': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Admin-Secret'
    }
}

api_extension = Api(
    api,
    title='Gatekeeper API Gateway',
    version='1.0',
    description='REST API for Data Amazon project.',
    doc='/docs',
    authorizations=authorizations
)

api_extension.add_namespace(datasets_ns)
api_extension.add_namespace(datasets_search_ns)
api_extension.add_namespace(datasets_filters_ns)

# api_extension.add_namespace(clients_ns)

api_extension.add_namespace(healthcheck_ns)
