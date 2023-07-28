import logging
from flask import Blueprint, Flask, request, jsonify, make_response
from app.services.datasets import DatasetService

datasets_bp = Blueprint('datasets', __name__, url_prefix='/datasets')
service = DatasetService()

@datasets_bp.get('/', defaults = {'dataset_id': None})
@datasets_bp.get('/<dataset_id>')
def fetch_dataset(dataset_id):
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
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.post('/')
def create_dataset():
    try:
        payload = request.get_json()
        service.create_dataset(payload)
        return make_response('', 201)
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.put('/<dataset_id>')
def update_dataset(dataset_id):
    try:
        payload = request.get_json()
        service.update_dataset(dataset_id, payload)
        return make_response('', 200)
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.delete('/<dataset_id>')
def disable_dataset(dataset_id):
    try:
        service.disable_dataset(dataset_id)
        response = make_response('', 200)
        return response
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.get('/filters')
def fetch_categories():
    try:
        return make_response(jsonify(service.fetch_available_filters()), 200)
    except Exception as e:
        logging.error(e)
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.get('/search')
def search_datasets():
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