# from uuid import UUID
# from fastapi import APIRouter, Depends, Request
# from controller.interceptor.user_parser import parse_user_header
# from container import Container
# from service.tus import TusService
# from dependency_injector.wiring import inject, Provide

# router = APIRouter(
#     prefix="/tus",
#     tags=["tus"],
#     responses={404: {"description": "Not found"}},
# )

# # POST /hooks
# @router.post("/hooks")
# @inject
# async def post(
#     request: Request,
#     user_id: UUID = Depends(parse_user_header),
#     service: TusService = Depends(Provide[Container.tus_service]),
# ) -> FileCreateResponse:
#     key = service.handle(name=payload.name, secret=payload.secret)
#     return FileCreateResponse(key=key)
