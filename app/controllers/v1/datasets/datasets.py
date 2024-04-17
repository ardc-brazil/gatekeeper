from flask import request, g
from app.controllers.interceptors.authentication import authenticate
from app.controllers.interceptors.authorization import authorize
from app.controllers.interceptors.tenancy_parser import parse_tenancy_header
from app.controllers.interceptors.user_parser import parse_user_header
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

data_file_model = namespace.model('DataFile', {
    'name': fields.String(required=True, description='Data file name'),
    'size_bytes': fields.Integer(required=True, description='File size in bytes'),
    'extension': fields.String(required=False, description='File extension'),
    'format': fields.String(required=False, description='File format'),
    'storage_file_name': fields.String(required=False, description='File name in storage'),
    'storage_path': fields.String(required=False, description='File path in storage'),
    'updated_at': fields.String(required=True, description='Data file updated at datetime'),
    'created_at': fields.String(required=True, description='Data file created at datetime'),
    'created_by': fields.String(required=True, description='Data file author id')
})

dataset_version_model = namespace.model('DatasetVersion', {
    'id': fields.String(readonly=True, required=True, description='Dataset Version ID'),
    'name': fields.String(readonly=True, required=True, description='Dataset version name'),
    'design_state': fields.String(readonly=True, required=True, description='The actual state of design'),
    'files': fields.List(fields.Nested(data_file_model), required=False, description='List of data files contained in version'),
    'updated_at': fields.String(required=True, description='Dataset version updated at datetime'),
    'created_at': fields.String(required=True, description='Dataset version created at datetime'),
    'created_by': fields.String(required=True, description='Dataset version author id'),
    'is_enabled': fields.Boolean(required=True, description='Dataset version status'),
})

dataset_model = namespace.model('Dataset', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID'),
    'name': fields.Raw(required=True, description='Dataset name'),
    'data': fields.String(required=False, description='Dataset information'),
    'is_enabled': fields.Boolean(required=True, description='Dataset status'),
    'updated_at': fields.String(required=True, description='Dataset updated at datetime'),
    'created_at': fields.String(required=True, description='Dataset created at datetime'),
    'tenancy': fields.String(required=False, description='Dataset tenancy'),
    'versions': fields.List(fields.Nested(dataset_version_model), required=False, description='Dataset current version'),
})

data_file_create_request_model = namespace.model('DataFileCreateRequest', {
    'name': fields.String(required=True, description='Data file name'),
    'size_bytes': fields.Integer(required=True, description='File size in bytes'),
    'extension': fields.String(required=False, description='File extension'),
    'format': fields.String(required=False, description='File format'),
    'storage_file_name': fields.String(required=False, description='File name in storage'),
    'storage_path': fields.String(required=False, description='File path in storage')
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

dataset_create_nested_response_model = namespace.model('DatasetCreateNested', {
    'id': fields.String(readonly=True, required=True, description='Dataset ID'),
    'design_state': fields.String(readonly=True, required=True, description='The actual state of design'),
})

dataset_version_create_nested_response_model = namespace.model('DatasetVersionNested', {
    'id': fields.String(readonly=True, required=True, description='Dataset Version ID'),
    'name': fields.String(readonly=True, required=True, description='Dataset version name'),
    'design_state': fields.String(readonly=True, required=True, description='The actual state of design'),
})

dataset_create_response_model = namespace.model('DatasetCreate', {
    'dataset': fields.Nested(dataset_create_nested_response_model, description='Dataset response model'),
    'version': fields.Nested(dataset_version_create_nested_response_model, description='Dataset version response model'),
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
    @namespace.param('latest_version', 'Flag to filter latest version of the dataset. Default is false')
    @namespace.param('version_design_state', 'Design state to be used in conjunction with "latest_version" param. Default is "DRAFT"')
    @namespace.param('version_is_enabled', 'Flag to filter enabled/disabled versions. Default is true')
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    @parse_user_header
    def get(self, dataset_id):
        '''Fetch a specific dataset'''
        dataset = service.fetch_dataset(dataset_id=dataset_id, 
                                        is_enabled=request.args.get('is_enabled'),
                                        user_id=g.user_id,
                                        tenancies=g.tenancies,
                                        latest_version=request.args.get('latest_version'),
                                        version_design_state=request.args.get('version_design_state', None),
                                        version_is_enabled=request.args.get('version_is_enabled', True))
        if (dataset is not None):
            return dataset
        else:
            raise NotFound()

    # PUT /api/v1/datasets/:dataset_id
    @namespace.doc("Update a Dataset")
    @namespace.expect(dataset_create_request_model, validate=True)
    @parse_tenancy_header
    @parse_user_header
    def put(self, dataset_id):
        '''Update a specific dataset'''
        payload = request.get_json()
        service.update_dataset(dataset_id=dataset_id, 
                               request_body=payload, 
                               user_id=g.user_id,
                               tenancies=g.tenancies)
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
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
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
    @namespace.param('version', 'A specific dataset version')
    @namespace.marshal_with(datasets_list_model)
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    @parse_user_header
    def get(self):
        '''Fetch all datasets'''
        query_params = {
            'categories': request.args.get('categories').split(',') if request.args.get('categories') else [],
            'level': request.args.get('level'),
            'data_types': request.args.get('data_types').split(',') if request.args.get('data_types') else [],
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'full_text': request.args.get('full_text'),
            'include_disabled': request.args.get('include_disabled', False),
            'version': request.args.get('version'),
        }

        datasets = service.search_datasets(query_params, 
                                           g.user_id,
                                           g.tenancies)
        payload =  {
            'content': datasets,
            'size': len(datasets)
        }

        return payload, 200
        
    # POST /api/v1/datasets
    @namespace.marshal_with(dataset_create_response_model)
    @namespace.expect(dataset_create_request_model, validate=True)
    @parse_user_header
    def post(self):
        '''Create a new dataset'''
        payload = request.get_json()
        return service.create_dataset(payload, g.user_id), 201

@namespace.route('/<string:dataset_id>/versions/<string:version>')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.param('version', 'The version name')
@namespace.doc(security=['api_key', 'api_secret', 'user_id'])
class DatasetsVersionController(Resource):

    method_decorators = [authenticate, authorize]

    # DELETE /api/v1/datasets/:dataset_id/versions/:version
    @namespace.doc("Disable a Dataset Version")
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    @parse_user_header
    def delete(self, dataset_id, version):
        '''Disable a specific dataset version'''
        service.disable_dataset_version(dataset_id=dataset_id, 
                                        user_id=g.user_id,
                                        version_name=version, 
                                        tenancies=g.tenancies)
        return {}, 200

@namespace.route('/<string:dataset_id>/versions/<string:version>/enable')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.param('version', 'The version name')
@namespace.response(404, 'Dataset or version not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret', 'user_id'])
class DatasetsVersionEnableController(Resource):

    method_decorators = [authenticate, authorize]

    # PUT /api/v1/datasets/:dataset_id/versions/:version/enable
    @namespace.doc("Enable a Dataset Version")
    @namespace.param('X-Datamap-Tenancies', 'List of user tenancies. Separated by comma', 'header')
    @parse_tenancy_header
    @parse_user_header
    def put(self, dataset_id, version):
        '''Enable a specific dataset version'''
        service.enable_dataset_version(dataset_id=dataset_id, 
                                        user_id=g.user_id,
                                        version_name=version, 
                                        tenancies=g.tenancies)
        return {}, 200


