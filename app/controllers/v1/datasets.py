import logging
from flask import request, jsonify, make_response
from app.controllers.interceptors.auth import public_route, requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound, InternalServerError

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')
dataset_model = namespace.model('Dataset', {
    'id': fields.String(
        readonly=True,
        required=True,
        description='Dataset ID'
    ),
    'name': fields.Raw(
        required=True,
        description='Dataset name'
    ),
    'data': fields.String(
        required=False,
        description='Dataset information'
    ),
    'is_enabled': fields.Boolean(
        required=True,
        description='Dataset status'
    )
})

dataset_create_model = namespace.model('DatasetCreate', {
    'id': fields.String(
        readonly=True,
        required=True,
        description='Dataset ID'
    )
})

@namespace.route('/<string:dataset_id>')
@namespace.param('dataset_id', 'The dataset identifier')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
class DatasetsController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Get a Dataset")
    @namespace.marshal_with(dataset_model)
    def get(self, dataset_id):
        '''Fetch a specific dataset'''
        try:
            dataset = service.fetch_dataset(dataset_id)
            if (dataset is not None):
                return dataset
            else:
                raise NotFound()
        except Exception as e:
            logging.error(e)
            raise InternalServerError()
    
    def put(self, dataset_id):
        try:
            payload = request.get_json()
            service.update_dataset(dataset_id, payload)
            return {}, 200
        except Exception as e:
            logging.error(e)
            raise InternalServerError()
    
    def delete(self, dataset_id):
        try:
            service.disable_dataset(dataset_id)
            return {}, 200
        except Exception as e:
            logging.error(e)
            raise InternalServerError()

@namespace.route('/')
@namespace.response(500, 'Internal Server error')
class DatasetsListController(Resource):

    method_decorators = [requires_auth]
    
    @namespace.marshal_list_with(dataset_model)
    def get(self):
        '''Fetch all datasets'''
        try:
            return service.fetch_all_datasets(), 200
        except Exception as e:
            logging.error(e)
            raise InternalServerError()
    
    @namespace.marshal_with(dataset_create_model)
    def post(self):
        try:
            payload = request.get_json()
            return {'id': service.create_dataset(payload)}, 201
        except Exception as e:
            logging.error(e)
            raise InternalServerError()