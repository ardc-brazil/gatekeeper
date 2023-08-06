import logging
from app.controllers.interceptors.auth import requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource
from app.controllers.v1.datasets.resources.datasets_models import dataset_filter_model
from werkzeug.exceptions import InternalServerError

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

@namespace.route('/filters')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class DatasetsFilterController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Get a Dataset filter")
    @namespace.marshal_list_with(dataset_filter_model)
    def get(self):
        try:
            return service.fetch_available_filters(), 200
        except Exception as e:
            logging.error(e)
            raise InternalServerError()
