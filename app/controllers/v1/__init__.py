from flask import Blueprint, url_for
from flask_restx import Api
from app.controllers.v1.datasets.datasets import namespace as datasets_ns
from app.controllers.v1.clients.clients import namespace as clients_ns
from app.controllers.v1.datasets.datasets_filters import namespace as datasets_filters_ns
from app.controllers.v1.infrastructure.infrastructure import namespace as healthcheck_ns

class PatchedApi(Api):
    @property
    def specs_url(self):
        return url_for(self.endpoint('specs'))
    
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

api_extension = PatchedApi(
    api,
    title='Gatekeeper API Gateway',
    version='1.0',
    description='REST API for Data Amazon project.',
    doc='/docs',
    authorizations=authorizations
)

api_extension.add_namespace(datasets_ns)
api_extension.add_namespace(datasets_filters_ns)

api_extension.add_namespace(clients_ns)

api_extension.add_namespace(healthcheck_ns)
