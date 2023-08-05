import logging
from flask import request, jsonify, make_response
from app.controllers.interceptors.auth import public_route, requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')
dataset_model = namespace.model('Dataset', {
    "id": fields.String(
        readonly=True,
        description='Hello world message'
    ) 
})

@namespace.route('/')
class DatasetsListController(Resource):

    method_decorators = [requires_auth]
    
    @namespace.marshal_list_with(dataset_model)
    @namespace.response(500, 'Internal Server error')
    def get(self, dataset_id=None):
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
            
    
    def post(self):
        try:
            payload = request.get_json()
            return make_response(jsonify({'id': service.create_dataset(payload)}), 201)
        except Exception as e:
            logging.error(e)
            response = make_response(jsonify({'error': 'An error occurred'}), 500)
            return response