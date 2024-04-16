from flask import request, jsonify, make_response
from functools import wraps

from app.exceptions.UnauthorizedException import UnauthorizedException
from app.services.auth import AuthService

auth_service = AuthService()

def authenticate(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Api-Key')
        api_secret = request.headers.get('X-Api-Secret')

        try: 
            auth_service.is_client_authorized(api_key, api_secret)
        except UnauthorizedException:
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        return f(*args, **kwargs)
    
    return decorated
