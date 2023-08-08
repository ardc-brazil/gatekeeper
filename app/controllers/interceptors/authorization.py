from flask import make_response, request, jsonify
from casbin import Enforcer
# from app.repositories.users import UsersRepository

def __get_user_from_request(request):
    return request.headers.get('X-Customer-Id')

# def __get_user(user_id):
#     return UsersRepository().fetch_by_id(user_id)

def authorization_middleware(enforcer: Enforcer):
    def middleware(next):
        def wrapper(*args, **kwargs):
            user_id = __get_user_from_request(request)
            user = {
                'id': user_id,
                'roles': ['admin', 'user']
            }
            # __get_user(user_id)

            resource = request.path
            action = request.method

            for role in user.roles:
                enforcer.add_role_for_user(user_id, role)
                
            if enforcer.enforce(user, resource, action):
                return next(*args, **kwargs)
            else:
                return make_response(jsonify({'message': 'Forbidden'}), 403)

        return wrapper
    return middleware