from functools import wraps
from flask import request, g

def parse_user_header(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = request.headers.get('X-User-Id')
        if user_id:
            g.user_id = user_id

        return f(*args, **kwargs)
    
    return decorated
