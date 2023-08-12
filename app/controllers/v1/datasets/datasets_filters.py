from app.controllers.interceptors.authentication import authenticate
from app.controllers.interceptors.authorization import authorize
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

dataset_filter_options_model = namespace.model('DatasetFilterOptions', {
    'id': fields.String(required=True, description='Options ID'),
    'label': fields.String(required=True, description='Options label'),
    'value': fields.String(required=True, description='Options value')
})

dataset_filter_model = namespace.model('DatasetFilter', {
    'id': fields.String(readonly=True, required=True, description='Filter ID'),
    'options': fields.List(fields.Nested(dataset_filter_options_model)),
    'selection': fields.String(required=True, description='Filter selection'),
    'title': fields.String(required=True, description='Filter title') 
})

@namespace.route('/filters')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class DatasetsFilterController(Resource):

    method_decorators = [authenticate, authorize]

    @namespace.doc("Get a Dataset filter")
    @namespace.marshal_list_with(dataset_filter_model)
    def get(self):
        '''Fetch dataset available filters'''
        return service.fetch_available_filters(), 200
        