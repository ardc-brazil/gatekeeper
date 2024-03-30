from flask import request, g
from app.controllers.interceptors.authentication import authenticate
from app.controllers.interceptors.authorization import authorize
from app.controllers.interceptors.tenancy_parser import parse_tenancy_header
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

dataset_model = namespace.model('Dataset', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID'),
    'name': fields.Raw(required=True, description='Dataset name'),
    'data': fields.String(required=False, description='Dataset information'),
    'is_enabled': fields.Boolean(required=True, description='Dataset status'),
    'updated_at': fields.String(required=True, description='Dataset updated at datetime'),
    'created_at': fields.String(required=True, description='Dataset created at datetime'),
    'tenancy': fields.String(required=False, description='Dataset tenancy')
})

dataset_create_request_model = namespace.model('DatasetCreateRequest', {
    'name': fields.String(required=True, description='Dataset name'),
    'data': fields.Raw(required=False, description='Dataset information in JSON format'),
    'tenancy': fields.String(required=True, description='Dataset tenancy')
})

dataset_update_request_model = namespace.model('DatasetUpdateRequest', {
    'name': fields.String(required=True, description='Dataset name'),
    'data': fields.Raw(required=False, description='Dataset information in JSON format'),
    'tenancy': fields.String(required=True, description='Dataset tenancy')
})

datasets_list_model = namespace.model('Datasets', {
    'content': fields.Nested(dataset_model, description='List of datasets'),
    'size': fields.Integer(required=False, description='Dataset information')
})

dataset_create_response_model = namespace.model('DatasetCreate', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID')
})

@namespace.route('/<string:dataset_id>')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret', 'user_id'])
class DatasetsController(Resource):

    method_decorators = [authenticate, authorize]

    # GET /api/v1/datasets/:dataset_id
    @namespace.doc("Get a Dataset")
    @namespace.marshal_with(dataset_model)
    @namespace.param('is_enabled', 'Flag to filter enabled datasets. Default is true')
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    def get(self, dataset_id):
        '''Fetch a specific dataset'''
        dataset = service.fetch_dataset(dataset_id, request.args.get('is_enabled'), g.tenancies)
        if (dataset is not None):
            return dataset
        else:
            raise NotFound()

    # PUT /api/v1/datasets/:dataset_id
    @namespace.expect(dataset_create_request_model, validate=True)
    def put(self, dataset_id):
        '''Update a specific dataset'''
        payload = request.get_json()
        service.update_dataset(dataset_id, payload)
        return {}, 200
    
    # DELETE /api/v1/datasets/:dataset_id
    @namespace.doc("Delete a Dataset")
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    def delete(self, dataset_id):
        '''Disable a specific dataset'''
        service.disable_dataset(dataset_id, g.tenancies)
        return {}, 200
    
@namespace.route('/<string:dataset_id>/enable')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret', 'user_id'])
class DatasetsEnableController(Resource):

    method_decorators = [authenticate, authorize]

    # PUT /api/v1/datasets/:dataset_id/enable
    @namespace.doc("Enable a Dataset")
    @parse_tenancy_header
    def put(self, dataset_id):
        '''Enable a specific dataset'''
        service.enable_dataset(dataset_id, g.tenancies)
        return {}, 200

@namespace.route('/')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret', 'user_id'])
class DatasetsListController(Resource):

    method_decorators = [authenticate, authorize]
    
    # GET /api/v1/datasets
    @namespace.doc('Search datasets')
    @namespace.param('categories', 'Dataset categories, comma separated')
    @namespace.param('level', 'Dataset level')
    @namespace.param('data_types', 'Dataset data types, comma separated')
    @namespace.param('date_from', 'Dataset date from, YYYY-MM-DD')
    @namespace.param('date_to', 'Dataset date to, YYYY-MM-DD')
    @namespace.param('full_text', 'Dataset full text')
    @namespace.param('include_disabled', 'True to include disabled Datasets')
    @namespace.marshal_with(datasets_list_model)
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    def get(self):
        '''Fetch all datasets'''
        query_params = {
            'categories': request.args.get('categories').split(',') if request.args.get('categories') else [],
            'level': request.args.get('level'),
            'data_types': request.args.get('data_types').split(',') if request.args.get('data_types') else [],
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'full_text': request.args.get('full_text'),
            'include_disabled': request.args.get('include_disabled', False)
        }

        datasets = service.search_datasets(query_params, g.tenancies)
        payload =  {
            'content': datasets,
            'size': len(datasets)
        }

        return payload, 200
        
    # POST /api/v1/datasets
    @namespace.marshal_with(dataset_create_response_model)
    @namespace.expect(dataset_create_request_model, validate=True)
    def post(self):
        '''Create a new dataset'''
        payload = request.get_json()
        return {'id': service.create_dataset(payload)}, 201
