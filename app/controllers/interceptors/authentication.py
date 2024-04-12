from flask import request, jsonify, make_response
from functools import wraps

from app.exceptions.UnauthorizedException import UnauthorizedException
from app.services.authentication import AuthenticationService

authentication_service = AuthenticationService()

def authenticate(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Api-Key')
        api_secret = request.headers.get('X-Api-Secret')

        try: 
            authentication_service.authenticate_client(api_key, api_secret)
        except UnauthorizedException as e:
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        return f(*args, **kwargs)
    
    return decorated
