import logging
from flask import make_response, request, jsonify
from casbin import Enforcer
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from functools import wraps
from postgresql_watcher import PostgresqlWatcher
import os

casbin_adapter = CasbinSQLAlchemyAdapter(os.environ['CASBIN_DATABASE_URL'])
enforcer = Enforcer('app/resources/casbin_model.conf', casbin_adapter)
watcher = PostgresqlWatcher(host=os.environ['CASBIN_WATCHER_HOST'],user='gk_admin',password='WYnAG9!qzhfx7hDatJcs',port=5432,dbname='gatekeeper_db')
watcher.set_update_callback(enforcer.load_policy)
enforcer.set_watcher(watcher)

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
        
        if not enforcer.enforce(user_id, resource, action):
            logging.info('User %s is not authorized to %s %s', user_id, action, resource)
            return make_response(jsonify({'message': 'Forbidden'}), 403)
        
        return f(*args, **kwargs)
        
    return decorated