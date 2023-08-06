
from flask_restx import Namespace, Resource

namespace = Namespace('health-check', 'Infrastructure operations')

@namespace.route('/')
class HealhCheckController(Resource):

	@namespace.doc("Get health check status")
	def get(self):
		return "success"