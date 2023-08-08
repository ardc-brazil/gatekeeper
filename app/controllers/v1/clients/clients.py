from flask import request
from flask_restx import Namespace, Resource, fields
from app.controllers.interceptors.authentication import requires_admin_auth
from app.controllers.interceptors.authorization import authorize
from app.services.clients import ClientsService
from werkzeug.exceptions import NotFound

service = ClientsService()
namespace = Namespace('clients', 'Clients operations')

client_model = namespace.model('Client', {
    'key': fields.String(readonly=True, required=True, description='Client key'),
    'name': fields.String(required=True, description='Client name'),
    'is_enabled': fields.Boolean(required=True, description='Is client enabled?')
})

client_create_model = namespace.model('ClientCreate', {
    'key': fields.String(readonly=True, required=True, description='Client key')
})

@namespace.route('/<string:key>')
@namespace.param('key', 'The client key')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security='api_admin_key')
class ClientsController(Resource):

    method_decorators = [requires_admin_auth, authorize]

    @namespace.doc("Get a Client")
    @namespace.marshal_with(client_model)
    def get(self, key):
        '''Fetch a specific client'''
        client = service.fetch(key)
        if (client is not None):
            return client, 200
        else:
            raise NotFound()
    
    @namespace.doc('Update a Client')
    def put(self, key):
        '''Update a specific client'''
        payload = request.get_json()
        service.update(key, payload)
        return {}, 200
            
    @namespace.doc('Disable a Client')
    def delete(self, key):
        '''Disable a specific client'''
        service.disable(key)
        return {}, 200
        
@namespace.route('/')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security='api_admin_key')
class ClientsListController(Resource):

    method_decorators = [requires_admin_auth, authorize]
    
    @namespace.marshal_list_with(client_model)
    def get(self):
        '''Fetch all clients'''
        return service.fetch_all(), 200

    @namespace.marshal_with(client_create_model)
    def post(self):
        '''Create a client'''
        payload = request.get_json()
        return {'key': service.create(payload)}, 201

@namespace.route('/<string:key>/enable')
@namespace.param('key', 'The client key')
@namespace.response(404, 'Dataset not found')
@namespace.response(500, 'Internal Server error')
@namespace.doc(security='api_admin_key')
class ClientsEnableController(Resource):

    method_decorators = [requires_admin_auth, authorize]

    @namespace.doc('Enable a Client')
    def put(self, key):
        '''Enable a specific client'''
        service.enable(key)
        return {}, 200