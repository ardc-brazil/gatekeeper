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

@namespace.route('/filters')        
class DatasetsFilterController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Get a Dataset filter")
    def get(self):
        try:
            return make_response(jsonify(service.fetch_available_filters()), 200)
        except Exception as e:
            logging.error(e)
            response = make_response(jsonify({'error': 'An error occurred'}), 500)
            return response