from flask import request
from functools import wraps

from app.services.clients import ClientsService
from app.services.secrets import check_password

from app.controllers.utils.http_messages import unauthorized

service = ClientsService()

__api_key_header = 'X-Api-Key'
__api_secret_header = 'X-Api-Secret'

def authenticate(f):
    '''Decorator to authenticate a client in the API'''
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get(__api_key_header)
        api_secret = request.headers.get(__api_secret_header)

        if api_key is None or api_secret is None:
            return unauthorized()

        client = service.fetch(api_key)
        
        if client is None:
            return unauthorized()
        
        if not check_password(api_secret, client['secret']):
            return unauthorized()

        return f(*args, **kwargs)
    
    return decorated
