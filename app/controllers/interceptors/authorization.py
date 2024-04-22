import json
from uuid import UUID
from flask import make_response, request, jsonify, g
from functools import wraps
from app.controllers.interceptors.authorization_container import AuthorizationContainer
from app.exceptions.UnauthorizedException import UnauthorizedException
from app.models.tus import TusResult
from app.services.auth import AuthService

auth_service = AuthService()

def __get_user_from_request(request) -> UUID:
    return UUID(request.headers.get('X-User-Id'))

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

def _adapt_tus_response(res: TusResult): 
    return {
        'HTTPResponse': {
            'StatusCode': res.status_code,
            'Body': json.dumps({
                'message': res.body_msg
            }),
            'Header': {
                'Content-Type': 'application/json'
            }
        }
    }

def authorize_tus(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_token = request.get_json()['Event']['HTTPRequest']['Header']['X-User-Token'][0]
        # TODO get user_id from token when available
        user_id = UUID(request.get_json()['Event']['HTTPRequest']['Header']['X-User-Id'][0])
        resource = request.path
        action = request.method

        try:
            auth_service.validate_jwt_and_decode(user_token)
            auth_service.is_user_authorized(user_id, resource, action)
            # set user_id in context
            g.user_id = user_id
        except UnauthorizedException as e:
            return make_response(_adapt_tus_response(TusResult(401, str(e), True)), 401)
        except Exception as e:
            return make_response(_adapt_tus_response(TusResult(500, str(e), True)), 500)
        
        return f(*args, **kwargs)
        
    return decorated