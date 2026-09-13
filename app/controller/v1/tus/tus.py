import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authorization import authorize_tus
from dependency_injector.wiring import inject, Provide

from app.controller.interceptor.user_parser import parse_tus_user_id
from app.logging_config import fields
from app.model.tus import TusResult
from app.service.tus import TusService

router = APIRouter(prefix="/tus", tags=["tus"], dependencies=[Depends(authorize_tus)])
logger = logging.getLogger("controller:tus")


def _adapt(res: TusResult) -> dict:
    if res.status_code == 200:
        return {}
    result = {
        "HTTPResponse": {
            "StatusCode": res.status_code,
            "Body": json.dumps({"message": res.body_msg}),
            "Header": {"Content-Type": "application/json"},
        }
    }

    if res.reject_upload is not None:
        result["RejectUpload"] = res.reject_upload

    return result


@router.post("/hooks")
@inject
async def post(
    payload: dict,
    response: Response,
    user_id: UUID = Depends(parse_tus_user_id),
    service: TusService = Depends(Provide[Container.tus_service]),
) -> dict:
    upload = payload.get("Event", {}).get("Upload", {})
    metadata = upload.get("MetaData", {})
    hook = fields(
        user_id=str(user_id),
        hook_type=payload.get("Type"),
        dataset_id=metadata.get("dataset_id"),
        filename=metadata.get("filename"),
        size_bytes=upload.get("Size"),
    )
    logger.info("tus hook received", extra=hook)

    res = service.handle(payload=payload, user_id=user_id)

    response.status_code = res.status_code
    response.body = json.dumps(_adapt(res)).encode()

    logger.info(
        "tus hook answered",
        extra={**hook, "status_code": res.status_code, "rejected": res.reject_upload},
    )

    return response
