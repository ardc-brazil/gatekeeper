from flask import request, jsonify
from functools import wraps

from app.repositories.clients import ClientsRepository
from app.services.secrets import hash_password

clients_repository = ClientsRepository()

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers['x-api-token']
        api_secret = request.headers['x-api-secret']

        client = clients_repository.fetch(api_key)
        
        if (client is None):
            return jsonify({'message': 'Unauthorized'}), 401
        
        hashed_key = hash_password(api_secret)

        if (hashed_key != client.secret):
            return jsonify({'message': 'Unauthorized'}), 401

        return f(*args, **kwargs)
    return decorated
