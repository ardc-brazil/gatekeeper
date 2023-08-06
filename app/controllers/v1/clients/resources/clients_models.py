from flask_restx import Namespace, fields

namespace = Namespace('clients', 'Clients operations')

client_model = namespace.model('Client', {
    'key': fields.String(readonly=True, required=True, description='Client key'),
    'name': fields.String(required=True, description='Client name'),
    'is_enabled': fields.Boolean(required=True, description='Is client enabled?')
})

client_create_model = namespace.model('ClientCreate', {
    'key': fields.String(readonly=True, required=True, description='Client key')
})