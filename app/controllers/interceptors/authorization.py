from flask import make_response, request, jsonify
from functools import wraps
from app.controllers.interceptors.authorization_container import AuthorizationContainer
from app.exceptions.UnauthorizedException import UnauthorizedException
from app.services.auth import AuthService

auth_service = AuthService()

def __get_user_from_request(request):
    return request.headers.get('X-User-Id')

def authorize(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = __get_user_from_request(request)
        resource = request.path
        action = request.method

        try: 
            auth_service.is_user_authorized(user_id, resource, action)
        except UnauthorizedException as e:
            if str(e) == 'missing_information':
               return make_response(jsonify({'message': 'Unauthorized'}), 401) 
            elif str(e) == 'not_authorized':
                return make_response(jsonify({'message': 'Forbidden'}), 403)
            else:
                return make_response(jsonify({'message': 'Forbidden'}), 403)

        return f(*args, **kwargs)
        
    return decorated