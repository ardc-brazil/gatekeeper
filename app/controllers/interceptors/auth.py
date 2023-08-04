import logging
from flask import request, jsonify
from functools import wraps

from app.repositories.clients import ClientsRepository
from app.services.clients import ClientsService
from app.services.secrets import check_password, hash_password

service = ClientsService()

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Api-Key')
        api_secret = request.headers.get('X-Api-Secret')

        if (api_key is None or api_secret is None):
            return jsonify({'message': 'Unauthorized'}), 401

        client = service.fetch(api_key)
        
        if (client is None):
            return jsonify({'message': 'Unauthorized'}), 401
        
        if not check_password(api_secret, client['secret']):
            return jsonify({'message': 'Unauthorized'}), 401

        return f(*args, **kwargs)
    return decorated
