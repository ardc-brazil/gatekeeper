import logging
from flask import request
from app.controllers.interceptors.auth import requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource
from werkzeug.exceptions import NotFound, InternalServerError
from app.controllers.v1.datasets.resources.datasets_models import dataset_model, dataset_create_model

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

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
        try:
            query_params = {
                'categories': request.args.get('categories').split(',') if request.args.get('categories') else [],
                'level': request.args.get('level'),
                'data_types': request.args.get('data_types').split(',') if request.args.get('data_types') else [],
                'date_from': request.args.get('date_from'),
                'date_to': request.args.get('date_to'),
                'full_text': request.args.get('full_text')
            }

            return service.search_datasets(query_params), 200
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