from flask import Blueprint, Flask, request, jsonify, make_response

from app.services.datasets import DatasetService

datasets_bp = Blueprint('datasets', __name__, url_prefix='/datasets')
service = DatasetService()

@datasets_bp.get('/', defaults = {'dataset_id': None})
@datasets_bp.get('/<dataset_id>')
def fetch_dataset(dataset_id):
    try:
        res = None
        print(dataset_id)
        if (dataset_id):
            res = make_response(jsonify(service.fetch_dataset(dataset_id)), 200)
        else:
            res = make_response(jsonify(service.fetch_all_datasets()), 200)
        return res
    except Exception as e:
        response = make_response(jsonify({'error': str(e)}), 500)
        return response

@datasets_bp.post('/')
def create_dataset():
    try:
        payload = request.get_json()
        res = service.create_dataset(payload)
        response = make_response(jsonify(res), 201)
        return response
    except Exception as e:
        response = make_response(jsonify({'error': str(e)}), 500)
        return response

@datasets_bp.put('/<dataset_id>')
def update_dataset(dataset_id):
    try:
        payload = request.get_json()
        res = service.update_dataset(dataset_id, payload)
        response = make_response(jsonify(res), 200)
        return response
    except Exception as e:
        response = make_response(jsonify({'error': str(e)}), 500)
        return response

@datasets_bp.delete('/<dataset_id>')
def disable_dataset(dataset_id):
    try:
        res = service.disable_dataset(dataset_id)
        response = make_response(jsonify(res), 200)
        return response
    except Exception as e:
        response = make_response(jsonify({'error': str(e)}), 500)
        return response
