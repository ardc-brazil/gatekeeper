from flask import Blueprint, jsonify, make_response, request
from app.controllers.interceptors.auth import requires_auth
from app.services.clients import ClientsService
from app.services.secrets import check_password, hash_password
import logging

clients_bp = Blueprint('clients', __name__, url_prefix='/clients')
service = ClientsService()

@clients_bp.before_request
def before_request():
    try: 
        secret = request.headers.get('X-Admin-Secret')
        if secret is None:
            return jsonify({'message': 'Unauthorized'}), 401
        if not check_password(secret, "$2b$12$W8b4N6emgwvuXuhsR.O0lO09E3w1YWXMn86aL4Eq5oP8TakRHEh.W"):
            return jsonify({'message': 'Unauthorized'}), 401
    except Exception as e:
        logging.error(e)
        return jsonify({'message': 'Unauthorized'}), 401

@clients_bp.get('/hash')
def hash_secret():
    secret = request.args.get('secret')
    if secret is None:
        return make_response(jsonify({'error': 'No secret provided'}), 400)
    hashed_secret = hash_password(secret)
    return make_response(jsonify({'hashed_secret': hashed_secret}), 200)

@clients_bp.get('/', defaults = {'key': None})
@clients_bp.get('/<key>')
def fetch_client(key):
    try:
        res = None
        if key:
            client = service.fetch(key)
            if (client is not None):
                res = make_response(jsonify(service.fetch(key)), 200)
            else:
                res = make_response(jsonify({}), 404)
        else:
            res = make_response(jsonify(service.fetch_all()), 200)
        return res
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response
    
@clients_bp.post('/')
def create_client():
    try:
        payload = request.get_json()
        return make_response(jsonify({'key': service.create(payload)}), 201)
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response
    
@clients_bp.put('/<key>')
def update_client(key):
    try:
        payload = request.get_json()
        service.update(key, payload)
        return make_response('', 200)
    except Exception:
        response = make_response(jsonify({'error': 'An error occurred'}), 500)
        return response