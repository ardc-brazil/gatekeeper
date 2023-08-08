from flask import request
from app.controllers.interceptors.authentication import requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

dataset_model = namespace.model('Dataset', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID'),
    'name': fields.Raw(required=True, description='Dataset name'),
    'data': fields.String(required=False, description='Dataset information'),
    'is_enabled': fields.Boolean(required=True, description='Dataset status')
})

dataset_create_model = namespace.model('DatasetCreate', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID')
})

@namespace.route('/<string:dataset_id>')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class DatasetsController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Get a Dataset")
    @namespace.marshal_with(dataset_model)
    def get(self, dataset_id):
        '''Fetch a specific dataset'''
        dataset = service.fetch_dataset(dataset_id)
        if (dataset is not None):
            return dataset
        else:
            raise NotFound()

    def put(self, dataset_id):
        '''Update a specific dataset'''
        payload = request.get_json()
        service.update_dataset(dataset_id, payload)
        return {}, 200
    
    def delete(self, dataset_id):
        '''Disable a specific dataset'''
        service.disable_dataset(dataset_id)
        return {}, 200

@namespace.route('/', strict_slashes=False)
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class DatasetsListController(Resource):

    method_decorators = [requires_auth]
    
    @namespace.doc("Search datasets")
    @namespace.param('categories', 'Dataset categories, comma separated')
    @namespace.param('level', 'Dataset level')
    @namespace.param('data_types', 'Dataset data types, comma separated')
    @namespace.param('date_from', 'Dataset date from, YYYY-MM-DD')
    @namespace.param('date_to', 'Dataset date to, YYYY-MM-DD')
    @namespace.param('full_text', 'Dataset full text')
    @namespace.marshal_list_with(dataset_model)
    def get(self):
        '''Fetch all datasets'''
        query_params = {
            'categories': request.args.get('categories').split(',') if request.args.get('categories') else [],
            'level': request.args.get('level'),
            'data_types': request.args.get('data_types').split(',') if request.args.get('data_types') else [],
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'full_text': request.args.get('full_text')
        }

        return service.search_datasets(query_params), 200
        
    @namespace.marshal_with(dataset_create_model)
    def post(self):
        '''Create a new dataset'''
        payload = request.get_json()
        return {'id': service.create_dataset(payload)}, 201
