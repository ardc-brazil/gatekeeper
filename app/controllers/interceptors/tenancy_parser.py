from functools import wraps
from flask import request, g

def parse_tenancy_header(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        tenancies = request.headers.get('X-Datamap-Tenancies')
        g.tenancies = []

        if tenancies:
            g.tenancies.extend(tenancy.strip() for tenancy in tenancies.split(','))

        return f(*args, **kwargs)
    
    return decorated