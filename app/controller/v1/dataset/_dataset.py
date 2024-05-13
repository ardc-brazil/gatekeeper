from flask import request, g
from app.controllers.interceptors.authentication import authenticate
from app.controllers.interceptors.authorization import authorize
from app.controllers.interceptors.tenancy_parser import parse_tenancy_header
from app.controllers.interceptors.user_parser import parse_user_header
from app.services.datasets import DatasetService
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import NotFound

service = DatasetService()
namespace = Namespace("datasets", "Dataset operations")

data_file_model = namespace.model(
    "DataFile",
    {
        "name": fields.String(required=True, description="Data file name"),
        "size_bytes": fields.Integer(required=True, description="File size in bytes"),
        "extension": fields.String(required=False, description="File extension"),
        "format": fields.String(required=False, description="File format"),
        "storage_file_name": fields.String(
            required=False, description="File name in storage"
        ),
        "storage_path": fields.String(
            required=False, description="File path in storage"
        ),
        "updated_at": fields.String(
            required=True, description="Data file updated at datetime"
        ),
        "created_at": fields.String(
            required=True, description="Data file created at datetime"
        ),
        "created_by": fields.String(required=True, description="Data file author id"),
    },
)

dataset_version_model = namespace.model(
    "DatasetVersion",
    {
        "id": fields.String(
            readonly=True, required=True, description="Dataset Version ID"
        ),
        "name": fields.String(
            readonly=True, required=True, description="Dataset version name"
        ),
        "design_state": fields.String(
            readonly=True, required=True, description="The actual state of design"
        ),
        "files": fields.List(
            fields.Nested(data_file_model),
            required=False,
            description="List of data files contained in version",
        ),
        "updated_at": fields.String(
            required=True, description="Dataset version updated at datetime"
        ),
        "created_at": fields.String(
            required=True, description="Dataset version created at datetime"
        ),
        "created_by": fields.String(
            required=True, description="Dataset version author id"
        ),
        "is_enabled": fields.Boolean(
            required=True, description="Dataset version status"
        ),
    },
)

dataset_model = namespace.model(
    "Dataset",
    {
        "id": fields.String(readonly=True, required=True, description="Dataset ID"),
        "name": fields.Raw(required=True, description="Dataset name"),
        "data": fields.String(required=False, description="Dataset information"),
        "is_enabled": fields.Boolean(required=True, description="Dataset status"),
        "updated_at": fields.String(
            required=True, description="Dataset updated at datetime"
        ),
        "created_at": fields.String(
            required=True, description="Dataset created at datetime"
        ),
        "tenancy": fields.String(required=False, description="Dataset tenancy"),
        "versions": fields.List(
            fields.Nested(dataset_version_model),
            required=False,
            description="Dataset all versions",
        ),
        "design_state": fields.String(
            readonly=True, required=True, description="The actual state of design"
        ),
        "current_version": fields.Nested(
            dataset_version_model, required=False, description="Dataset current version"
        ),
    },
)

data_file_create_request_model = namespace.model(
    "DataFileCreateRequest",
    {
        "name": fields.String(required=True, description="Data file name"),
        "size_bytes": fields.Integer(required=True, description="File size in bytes"),
        "extension": fields.String(required=False, description="File extension"),
        "format": fields.String(required=False, description="File format"),
        "storage_file_name": fields.String(
            required=False, description="File name in storage"
        ),
        "storage_path": fields.String(
            required=False, description="File path in storage"
        ),
    },
)

dataset_create_request_model = namespace.model(
    "DatasetCreateRequest",
    {
        "name": fields.String(required=True, description="Dataset name"),
        "data": fields.Raw(
            required=False, description="Dataset information in JSON format"
        ),
        "tenancy": fields.String(required=True, description="Dataset tenancy"),
    },
)

dataset_update_request_model = namespace.model(
    "DatasetUpdateRequest",
    {
        "name": fields.String(required=True, description="Dataset name"),
        "data": fields.Raw(
            required=False, description="Dataset information in JSON format"
        ),
        "tenancy": fields.String(required=True, description="Dataset tenancy"),
    },
)

datasets_list_model = namespace.model(
    "Datasets",
    {
        "content": fields.Nested(dataset_model, description="List of datasets"),
        "size": fields.Integer(required=False, description="Dataset information"),
    },
)

dataset_create_nested_response_model = namespace.model(
    "DatasetCreateNested",
    {
        "id": fields.String(readonly=True, required=True, description="Dataset ID"),
        "design_state": fields.String(
            readonly=True, required=True, description="The actual state of design"
        ),
    },
)

dataset_version_create_nested_response_model = namespace.model(
    "DatasetVersionNested",
    {
        "id": fields.String(
            readonly=True, required=True, description="Dataset Version ID"
        ),
        "name": fields.String(
            readonly=True, required=True, description="Dataset version name"
        ),
        "design_state": fields.String(
            readonly=True, required=True, description="The actual state of design"
        ),
    },
)

dataset_create_response_model = namespace.model(
    "DatasetCreate",
    {
        "dataset": fields.Nested(
            dataset_create_nested_response_model, description="Dataset response model"
        ),
        "version": fields.Nested(
            dataset_version_create_nested_response_model,
            description="Dataset version response model",
        ),
    },
)




@namespace.route("/<string:dataset_id>/versions/<string:version>/enable")
@namespace.param("dataset_id", "The dataset identifier")
@namespace.param("version", "The version name")
@namespace.response(404, "Dataset or version not found")
@namespace.response(500, "Internal Server error")
@namespace.doc(security=["api_key", "api_secret", "user_id"])
class DatasetsVersionEnableController(Resource):
    method_decorators = [authenticate, authorize]

    # PUT /api/v1/datasets/:dataset_id/versions/:version/enable
    @namespace.doc("Enable a Dataset Version")
    @namespace.param(
        "X-Datamap-Tenancies", "List of user tenancies. Separated by comma", "header"
    )
    @parse_tenancy_header
    @parse_user_header
    def put(self, dataset_id, version):
        """Enable a specific dataset version"""
        service.enable_dataset_version(
            dataset_id=dataset_id,
            user_id=g.user_id,
            version_name=version,
            tenancies=g.tenancies,
        )
        return {}, 200
