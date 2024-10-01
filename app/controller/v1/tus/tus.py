import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authorization import authorize_tus
from dependency_injector.wiring import inject, Provide

from app.controller.interceptor.user_parser import parse_tus_user_id
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
    logger.debug(payload)
    payload_type = payload["Type"]
    payload_event_upload = payload["Event"]["Upload"]
    logger.info(
        f"user_id={user_id} payload.type={payload_type} payload.event.upload={payload_event_upload}"
    )

    res = service.handle(payload=payload, user_id=user_id)

    response.status_code = res.status_code
    response.body = json.dumps(_adapt(res)).encode()

    logger.info(f"status_code={res.status_code}")

    return response
