import logging
from flask import request, jsonify, make_response
from app.controllers.interceptors.auth import public_route, requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

@requires_auth
@namespace.route('/<string:dataset_id>')
@namespace.response(404, 'Dataset not found')
@namespace.param('dataset_id', 'The dataset identifier')
class DatasetsController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Get a Dataset")
    # @namespace.marshal_list_with(dataset_model)
    @namespace.response(500, 'Internal Server error')
    def get(self, dataset_id=None):
            '''Fetch a specifica dataset'''
            try:
                res = None
                if (dataset_id):
                    dataset = service.fetch_dataset(dataset_id)
                    if (dataset is not None):
                        res = make_response(jsonify(service.fetch_dataset(dataset_id)), 200)
                    else:
                        res = make_response(jsonify({}), 404)
                else:
                    res = make_response(jsonify(service.fetch_all_datasets()), 200)
                return res
            except Exception as e:
                logging.error(e)
                response = make_response(jsonify({'error': 'An error occurred'}), 500)
                return response
    
    def put(self, dataset_id):
        try:
            payload = request.get_json()
            service.update_dataset(dataset_id, payload)
            return make_response('', 200)
        except Exception as e:
            logging.error(e)
            response = make_response(jsonify({'error': 'An error occurred'}), 500)
            return response
    
    def delete(self, dataset_id):
        try:
            service.disable_dataset(dataset_id)
            response = make_response('', 200)
            return response
        except Exception as e:
            logging.error(e)
            response = make_response(jsonify({'error': 'An error occurred'}), 500)
            return response
