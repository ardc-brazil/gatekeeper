# from app.controllers.interceptors.authentication import authenticate
# from app.controllers.interceptors.authorization import authorize
# from app.controllers.utils.method_decorator import decorate_per_method
# from app.services.users import UsersService
# from flask_restx import Namespace, Resource, fields
# from werkzeug.exceptions import NotFound
# from flask import request

# service = UsersService()
# namespace = Namespace('users', 'Users operations')

# provider_model = namespace.model('Provider', {
#     'name': fields.String(required=True, description='Provider name'),
#     'reference': fields.String(required=True, description='Provider reference')
# })

# user_model = namespace.model('User', {
#     'id': fields.String(readonly=True, required=True, description='User id'),
#     'name': fields.String(required=True, description='User name'),
#     'email': fields.String(required=False, description='User email'),
#     'roles': fields.List(fields.String, required=False, description='User roles'),
#     'providers': fields.List(fields.Nested(provider_model), required=False, description='User providers'),
#     'is_enabled': fields.Boolean(required=True, description='Is user enabled?'),
#     'created_at': fields.DateTime(required=True, description='User creation date'),
#     'updated_at': fields.DateTime(required=True, description='User last update date')
# })

# user_create_response_model = namespace.model('UserCreateResponse', {
#     'id': fields.String(readonly=True, required=True, description='User id')
# })

# user_create_request_model = namespace.model('UserCreateRequest', {
#     'name': fields.String(required=True, description='User name'),
#     'email': fields.String(required=False, description='User email'),
#     'providers': fields.List(fields.Nested(provider_model), required=False, description='User providers'),
#     'roles': fields.List(fields.String, required=False, description='User roles')
# })

# user_role_add_model = namespace.model('UserRoleAdd', {
#     'roles': fields.List(fields.String, required=True, description='User roles')
# })

# user_provider_add_model = namespace.model('UserProviderAdd', {
#     'provider': fields.String(required=True, description='User provider'),
#     'reference': fields.String(required=True, description='User provider reference')
# })

# @namespace.route('/<string:id>')
# @namespace.param('id', 'The user id')
# @namespace.response(404, 'User not found')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret', 'user_id'])
# class UsersController(Resource):
        
#     method_decorators = [authenticate, authorize]

#     @namespace.doc("Get a User")
#     @namespace.marshal_with(user_model)
#     @namespace.param('is_enabled', 'Flag to filter enabled users. Default is true')
#     def get(self, id):
#         '''Fetch a specific user'''
#         user = service.fetch_by_id(id, request.args.get('is_enabled'))
#         if (user is not None):
#             return user, 200
#         else:
#             raise NotFound()

#     @namespace.doc('Update a User')
#     def put(self, id):
#         '''Update a specific user'''
#         payload = request.get_json()
#         service.update(id, payload)
#         return {}, 200
    
#     @namespace.doc('Disable a User')
#     def delete(self, id):
#         '''Disable a specific user'''
#         service.disable(id)
#         return {}, 200

# @namespace.route('/')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret', 'user_id'])
# class UsersListController(Resource):
    
#         method_decorators = [authenticate, decorate_per_method(['get'], authorize)]
        
#         @namespace.doc('Search users')
#         @namespace.param('email', 'User email')
#         @namespace.param('is_enabled', 'Flag to filter enabled users. Default is true')
#         @namespace.marshal_list_with(user_model)
#         def get(self):
#             '''Fetch all users'''
#             query_params = {
#                 'email' : request.args.get('email'),
#                 'is_enabled' : request.args.get('is_enabled')
#             }
#             return service.search(query_params), 200
    
#         @namespace.marshal_with(user_create_response_model)
#         @namespace.expect(user_create_request_model, validate=True)
#         def post(self):
#             '''Create a user'''
#             payload = request.get_json()
#             return {'id': service.create(payload)}, 201

# @namespace.route('/<string:id>/enable')
# @namespace.param('id', 'The user id')
# @namespace.response(404, 'User not found')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret', 'user_id'])
# class UsersEnableController(Resource):
    
#     method_decorators = [authenticate, authorize]
    
#     @namespace.doc('Enable a User')
#     def put(self, id):
#         '''Enable a specific user'''
#         service.enable(id)
#         return {}, 200
    
# @namespace.route('/<string:id>/roles')
# @namespace.param('id', 'The user id')
# @namespace.response(404, 'User not found')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret', 'user_id'])
# class UsersRolesController(Resource):
    
#     method_decorators = [authorize]
    
#     @namespace.doc('Add roles to a User')
#     @namespace.expect(user_role_add_model, validate=True)
#     def put(self, id):
#         '''Add roles to a specific user'''
#         payload = request.get_json()
#         service.add_roles(id, payload['roles'])
#         return {}, 200
    
#     @namespace.doc('Remove roles from a User')
#     @namespace.expect(user_role_add_model, validate=True)
#     def delete(self, id):
#         '''Remove roles from a specific user'''
#         payload = request.get_json()
#         service.remove_roles(id, payload['roles'])
#         return {}, 200

# @namespace.route('/<string:id>/providers')
# @namespace.param('id', 'The user id')
# @namespace.response(404, 'User not found')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret', 'user_id'])
# class UsersProvidersController(Resource):
        
#         method_decorators = [authenticate, authorize]
        
#         @namespace.doc('Add provider to a User')
#         @namespace.expect(user_provider_add_model, validate=True)
#         def put(self, id):
#             '''Add provider to a specific user'''
#             payload = request.get_json()
#             service.add_provider(id, payload['provider'], payload['reference'])
#             return {}, 200
        
#         @namespace.doc('Remove provider from a User')
#         @namespace.expect(user_provider_add_model, validate=True)
#         def delete(self, id):
#             '''Remove provider from a specific user'''
#             payload = request.get_json()
#             service.remove_provider(id, payload['provider'], payload['reference'])
#             return {}, 200
        
# @namespace.route('/providers/<string:provider_name>/<string:reference>')
# @namespace.param('provider_name', 'The provider name')
# @namespace.param('reference', 'The provider reference')
# @namespace.response(404, 'User not found')
# @namespace.response(500, 'Internal Server error')
# @namespace.doc(security=['api_key', 'api_secret'])
# class UsersGetByProviderController(Resource):
            
#     method_decorators = [authenticate]
    
#     @namespace.doc('Get a User by provider')
#     @namespace.marshal_with(user_model)
#     def get(self, provider_name, reference):
#         '''Fetch a specific user by provider'''
#         user = service.fetch_by_provider(provider_name, reference)
#         if (user is not None):
#             return user, 200
#         else:
#             raise NotFound()
