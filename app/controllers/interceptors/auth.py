import logging
from flask import request, jsonify, make_response
from functools import wraps

from app.repositories.clients import ClientsRepository
from app.services.clients import ClientsService
from app.services.secrets import check_password, hash_password

service = ClientsService()

def public_route(decorated_function):
    """
    This is a decorator to specify public endpoints in our flask routes
    :param decorated_function:
    :return:
    """
    decorated_function.is_public = True
    return decorated_function


def _perform_auth(method):
    is_public_endpoint = getattr(method, 'is_public', False)
    # place the validation here
    print("ispub", is_public_endpoint)

    return method


def requires_auth(f):
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
