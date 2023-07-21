from flask import Blueprint, Flask, request, jsonify, make_response
from app.services.datasets import DatasetService
import logging

datasets_bp = Blueprint('datasets', __name__, url_prefix='/datasets')
service = DatasetService()

@datasets_bp.get('/', defaults = {'dataset_id': None})
@datasets_bp.get('/<dataset_id>')
def fetch_dataset(dataset_id):
    try:
        res = None
        print(dataset_id)
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

@datasets_bp.post('/')
def create_dataset():
    try:
        payload = request.get_json()
        service.create_dataset(payload)
        return make_response('', 201)
    except Exception as e:
        logging.error(e)
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.put('/<dataset_id>')
def update_dataset(dataset_id):
    try:
        payload = request.get_json()
        service.update_dataset(dataset_id, payload)
        return make_response('', 200)
    except Exception as e:
        logging.error(e)
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response

@datasets_bp.delete('/<dataset_id>')
def disable_dataset(dataset_id):
    try:
        service.disable_dataset(dataset_id)
        response = make_response('', 200)
        return response
    except Exception as e:
        logging.error(e)
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response
