from app.controllers.interceptors.authentication import requires_auth
from app.services.users import UsersService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound
from flask import request

service = UsersService()
namespace = Namespace('users', 'Users operations')

user_model = namespace.model('User', {
    'id': fields.String(readonly=True, required=True, description='User id'),
    'name': fields.String(required=True, description='User name'),
    'email': fields.String(required=False, description='User email'),
    'roles': fields.List(fields.String, required=False, description='User roles'),
    'providers': fields.List(fields.String, required=False, description='User providers'),
    'is_enabled': fields.Boolean(required=True, description='Is user enabled?')
})

user_create_model = namespace.model('UserCreate', {
    'id': fields.String(readonly=True, required=True, description='User id')
})

user_role_add_model = namespace.model('UserRoleAdd', {
    'roles': fields.List(fields.String, required=True, description='User roles')
})

user_provider_add_model = namespace.model('UserProviderAdd', {
    'provider': fields.String(required=True, description='User provider')
})

@namespace.route('/<string:id>')
@namespace.param('id', 'The user id')
@namespace.response(404, 'User not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class UsersController(Resource):
        
    method_decorators = [requires_auth]

    @namespace.doc("Get a User")
    @namespace.marshal_with(user_model)
    def get(self, id):
        '''Fetch a specific user'''
        user = service.fetch_by_id(id)
        if (user is not None):
            return user, 200
        else:
            raise NotFound()

    @namespace.doc('Update a User')
    def put(self, id):
        '''Update a specific user'''
        payload = request.get_json()
        service.update(id, payload)
        return {}, 200
    
    @namespace.doc('Disable a User')
    def delete(self, id):
        '''Disable a specific user'''
        service.disable(id)
        return {}, 200

@namespace.route('/')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security=['api_key', 'api_secret'])
class UsersListController(Resource):
    
        method_decorators = [requires_auth]
        
        @namespace.marshal_list_with(user_model)
        def get(self):
            '''Fetch all users'''
            return service.fetch_all(), 200
    
        @namespace.marshal_with(user_create_model)
        def post(self):
            '''Create a user'''
            payload = request.get_json()
            return {'id': service.create(payload)}, 201

@namespace.route('/<string:id>/enable')
@namespace.param('id', 'The user id')
@namespace.response(404, 'User not found')
@namespace.response(500, 'Internal Server error')
class UsersEnableController(Resource):
    
    method_decorators = [requires_auth]
    
    @namespace.doc('Enable a User')
    def put(self, id):
        '''Enable a specific user'''
        service.enable(id)
        return {}, 200
    
@namespace.route('/<string:id>/roles')
@namespace.param('id', 'The user id')
@namespace.response(404, 'User not found')
@namespace.response(500, 'Internal Server error')
class UsersRolesController(Resource):
    
    method_decorators = [requires_auth]
    
    @namespace.doc('Add roles to a User')
    def put(self, id):
        '''Add roles to a specific user'''
        payload = request.get_json()
        service.add_roles(id, payload['roles'])
        return {}, 200
    
    @namespace.doc('Remove roles from a User')
    def delete(self, id):
        '''Remove roles from a specific user'''
        payload = request.get_json()
        service.remove_roles(id, payload['roles'])
        return {}, 200

@namespace.route('/<string:id>/providers')
@namespace.param('id', 'The user id')
@namespace.response(404, 'User not found')
@namespace.response(500, 'Internal Server error')
class UsersProvidersController(Resource):
        
        method_decorators = [requires_auth]
        
        @namespace.doc('Add provider to a User')
        def put(self, id):
            '''Add provider to a specific user'''
            payload = request.get_json()
            service.add_provider(id, payload['provider'])
            return {}, 200
        
        @namespace.doc('Remove provider from a User')
        def delete(self, id):
            '''Remove provider from a specific user'''
            payload = request.get_json()
            service.remove_provider(id, payload['provider'])
            return {}, 200
