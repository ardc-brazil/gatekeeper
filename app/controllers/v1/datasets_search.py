import logging
from flask import request, jsonify, make_response
from app.controllers.interceptors.auth import public_route, requires_auth
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields

service = DatasetService()
namespace = Namespace('datasets', 'Dataset operations')

@namespace.route('/search')        
class DatasetsSearchController(Resource):

    method_decorators = [requires_auth]

    @namespace.doc("Search datasets")
    def get(self):
        try:
            query_params = {
                'categories': request.args.get('categories').split(',') if request.args.get('categories') else [],
                'level': request.args.get('level'),
                'data_types': request.args.get('data_types').split(',') if request.args.get('data_types') else [],
                'date_from': request.args.get('date_from'),
                'date_to': request.args.get('date_to'),
                'full_text': request.args.get('full_text')
            }

            return make_response(jsonify(service.search_datasets(query_params)), 200)
        except Exception as e:
            logging.error(e)
            response = make_response(jsonify({'error': 'An error occurred'}), 500)
            return response