import logging
from flask import request, jsonify, make_response
from functools import wraps

from app.services.clients import ClientsService
from app.services.secrets import check_password

service = ClientsService()

def authenticate(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Api-Key')
        api_secret = request.headers.get('X-Api-Secret')

        if (api_key is None or api_secret is None):
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        client = service.fetch(api_key)
        
        if (client is None):
            return make_response(jsonify({'message': 'Unauthorized'}), 401)
        
        if not check_password(api_secret, client['secret']):
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        return f(*args, **kwargs)
    
    return decorated
