# from flask import Blueprint, jsonify, make_response, request
# from flask_restx import Namespace, Resource
# from app.controllers.interceptors.auth import requires_admin_auth, requires_auth
# from app.services.clients import ClientsService
# from app.services.secrets import check_password, hash_password
# import logging

# service = ClientsService()
# namespace = Namespace('clients', 'Clients operations')

# @namespace.route('/clients')
# @namespace.param('key', 'The client identifier', 'body')
# class ClientsController(Resource):
#     method_decorators = [requires_admin_auth]

#     @namespace.route('/<string:key>')
#     @namespace.doc("Get a Client")
#     def get(self, key):
#         try:
#             res = None
#             if key:
#                 client = service.fetch(key)
#                 if (client is not None):
#                     res = make_response(jsonify(service.fetch(key)), 200)
#                 else:
#                     res = make_response(jsonify({}), 404)
#             else:
#                 res = make_response(jsonify(service.fetch_all()), 200)
#             return res
#         except Exception:
#             response = make_response(jsonify({'error': 'An error occurred'}), 500)
#             return response
    
#     @namespace.doc('Create a Client')
#     def post(self, ):
#         try:
#             payload = request.get_json()
#             return make_response(jsonify({'key': service.create(payload)}), 201)
#         except Exception:
#             response = make_response(jsonify({'error': 'An error occurred'}), 500)
#             return response
    
#     @namespace.route('/<key>')
#     @namespace.doc('Update a Client')
#     def put(self, key):
#         try:
#             payload = request.get_json()
#             service.update(key, payload)
#             return make_response('', 200)
#         except Exception:
#             response = make_response(jsonify({'error': 'An error occurred'}), 500)
#             return response

#     @namespace.doc('Disable a Client')
#     def delete(key):
#         try:
#             service.disable(key)
#             return make_response('', 200)
#         except Exception:
#             response = make_response(jsonify({'error': 'An error occurred'}), 500)
#             return response

#     @namespace.route('/clients/<string:key>/enable')
#     @namespace.doc('Enable a Client')
#     def put(key):
#         try:
#             service.enable(key)
#             return make_response('', 200)
#         except Exception:
#             response = make_response(jsonify({'error': 'An error occurred'}), 500)
#             return response