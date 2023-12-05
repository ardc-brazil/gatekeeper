import logging
from flask import make_response, request, jsonify
from functools import wraps
from app.controllers.interceptors.authorizar_container import AuthorizerContainer

def __get_user_from_request(request):
    return request.headers.get('X-User-Id')

def authorize(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = __get_user_from_request(request)
        
        if user_id is None:
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        resource = request.path
        action = request.method

        if not AuthorizerContainer.instance().getEnforcer().enforce(user_id, resource, action):
            logging.info('User %s is not authorized to %s %s', user_id, action, resource)
            return make_response(jsonify({'message': 'Forbidden'}), 403)
        
        return f(*args, **kwargs)
        
    return decorated