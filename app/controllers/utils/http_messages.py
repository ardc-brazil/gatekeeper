from flask import jsonify, make_response

__unauthorized = 'Unauthorized'
__forbidden = 'Forbidden'
__user_id_header = 'X-User-Id'

def unauthorized():
    return make_response(jsonify({'message': __unauthorized}), 401)

def forbidden():
    return make_response(jsonify({'message': __forbidden}), 403)

def get_user_from_request(request):
    request.headers.get(__user_id_header)
