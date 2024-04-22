from app.controllers.interceptors.authentication import authenticate
from app.controllers.interceptors.authorization import authorize
from app.controllers.utils.method_decorator import decorate_per_method
from app.services.tenancies import TenancyService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound
from flask import request

service = TenancyService()
namespace = Namespace("tenancies", "Tenancy operations")

tenancy_model = namespace.model(
    "Tenancy",
    {
        "name": fields.String(required=True, description="Tenancy name"),
        "is_enabled": fields.Boolean(required=True, description="Is tennacy enabled?"),
        "created_at": fields.String(required=True, description="Tenancy creation date"),
        "updated_at": fields.String(
            required=True, description="Tenancy last update date"
        ),
    },
)

tenancy_create_request_model = namespace.model(
    "TenancyCreateRequest",
    {
        "name": fields.String(required=True, description="Tenancy name"),
    },
)

tenancy_update_request_model = namespace.model(
    "TenancyUpdateRequest",
    {
        "name": fields.String(required=True, description="Tenancy name"),
        "is_enabled": fields.Boolean(required=True, description="Is tennacy enabled?"),
    },
)


@namespace.route("/<string:name>")
@namespace.param("name", "The tenancy")
@namespace.response(404, "Tenancy not found")
@namespace.response(500, "Internal Server error")
@namespace.doc(security=["api_key", "api_secret", "user_id"])
class TenanciesController(Resource):
    method_decorators = [authenticate, authorize]

    @namespace.doc("Get a User")
    @namespace.marshal_with(tenancy_model)
    @namespace.param("is_enabled", "Flag to filter enabled tenancies. Default is true")
    def get(self, name):
        """Fetch a specific tenancy"""
        user = service.fetch(name, request.args.get("is_enabled"))
        if user is not None:
            return user, 200
        else:
            raise NotFound()

    @namespace.doc("Update a Tenancy")
    @namespace.expect(tenancy_update_request_model, validate=True)
    def put(self, name):
        """Update a specific tenancy"""
        payload = request.get_json()
        service.update(name, payload)
        return {}, 200

    @namespace.doc("Disable a Tenancy")
    def delete(self, name):
        """Disable a specific tenancy"""
        service.disable(name)
        return {}, 200


@namespace.route("/")
@namespace.response(500, "Internal Server error")
@namespace.doc(security=["api_key", "api_secret", "user_id"])
class TenanciesListController(Resource):
    method_decorators = [authenticate, decorate_per_method(["get"], authorize)]

    @namespace.doc("Fetch all tenancies")
    @namespace.param("is_enabled", "Flag to filter enabled tenancies. Default is true")
    @namespace.marshal_list_with(tenancy_model)
    def get(self):
        """Fetch all tenancies"""
        return service.fetch_all(request.args.get("is_enabled")), 200

    @namespace.expect(tenancy_create_request_model, validate=True)
    def post(self):
        """Create a tenancy"""
        payload = request.get_json()
        service.create(payload)
        return {}, 201


@namespace.route("/<string:name>/enable")
@namespace.param("name", "The tenancy name")
@namespace.response(404, "Tenancy not found")
@namespace.response(500, "Internal Server error")
@namespace.doc(security=["api_key", "api_secret", "user_id"])
class TenancyEnableController(Resource):
    method_decorators = [authenticate, authorize]

    @namespace.doc("Enable a Tenancy")
    def put(self, name):
        """Enable a specific tenancy"""
        service.enable(name)
        return {}, 200
