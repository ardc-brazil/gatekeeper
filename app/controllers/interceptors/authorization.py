from flask import make_response, request, jsonify
from casbin import Enforcer

def __get_user_from_requiest(request):
    return request.headers.get('X-Customer-Id')

def authorization_middleware(enforcer: Enforcer):
    def middleware(next):
        def wrapper(*args, **kwargs):
            user = __get_user_from_requiest(request)
            recurso = request.path
            acao = request.method

            if enforcer.enforce(user, recurso, acao):
                return next(*args, **kwargs)
            else:
                return make_response(jsonify({'message': 'Acesso negado'}), 403)

        return wrapper
    return middleware