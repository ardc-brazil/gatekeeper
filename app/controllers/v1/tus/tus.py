import json
from flask_restx import Namespace, Resource
from flask import request, g

from app.controllers.interceptors.authorization import authorize_tus
from app.models.tus import TusResult
from app.services.tus import TusService

namespace = Namespace('tus', 'Tus operations')
service = TusService()

@namespace.route('/hooks')
class TusController(Resource):

    method_decorators = [authorize_tus]

    def _adapt(self, res: TusResult):
        if res.status_code == 200:
            return {}, 200
        result = {
            'HTTPResponse': {
                'StatusCode': res.status_code,
                'Body': json.dumps({
                    'message': res.body_msg
                }),
                'Header': {
                    'Content-Type': 'application/json'
                }
            }
        }

        if not res.reject_upload is None:
            result['RejectUpload'] = res.reject_upload

        return result, res.status_code
    
    @namespace.doc('Handle TUS web hooks')
    def post(self):
        '''Receive TUS HTTP hooks'''
        res = service.handle(request.get_json(), g.user_id)
        
        return self._adapt(res)
