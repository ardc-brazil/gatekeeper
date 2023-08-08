from flask import make_response, request, jsonify
from casbin import Enforcer
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from functools import wraps
from postgresql_watcher import PostgresqlWatcher

casbin_adapter = CasbinSQLAlchemyAdapter('postgresql://gk_admin:WYnAG9!qzhfx7hDatJcs@localhost:5432/gatekeeper_db')
enforcer = Enforcer('app/resources/casbin_policy.conf', casbin_adapter)
watcher = PostgresqlWatcher(host='localhost',user='gk_admin',password='WYnAG9!qzhfx7hDatJcs',port=5432,dbname='gatekeeper_db')
watcher.set_update_callback(enforcer.load_policy)
enforcer.set_watcher(watcher)

def __get_user_from_request(request):
    return request.headers.get('X-Customer-Id')

def authorize(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = __get_user_from_request(request)
        
        if user_id is None:
            return make_response(jsonify({'message': 'Unauthorized'}), 401)

        resource = request.path
        action = request.method
        
        if not enforcer.enforce(user_id, resource, action):
            return make_response(jsonify({'message': 'Forbidden'}), 403)
        
        return f(*args, **kwargs)
        
    return decorated