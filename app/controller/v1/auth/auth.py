from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response

from app.container import Container
from app.controller.interceptor.authentication import authenticate
from app.controller.v1.auth.resource import (
    ChallengeResponse,
    CodeRequest,
    EmailVerificationRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SignUpRequest,
    UserIdResponse,
)
from app.exception.not_found import NotFoundException
from app.service.account import AccountService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(authenticate)],
)


def _challenge_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise NotFoundException("challenge_not_found") from None


@router.post("/sign-up", status_code=202, response_model=ChallengeResponse)
@inject
def sign_up(
    body: SignUpRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> ChallengeResponse:
    return ChallengeResponse(
        challenge_id=service.sign_up(body.name, body.email, body.password)
    )


@router.post("/sign-up/{challenge_id}/confirm", response_model=UserIdResponse)
@inject
def confirm_sign_up(
    challenge_id: str,
    body: CodeRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(
        user_id=service.confirm_sign_up(_challenge_id(challenge_id), body.code)
    )


@router.post("/email-verifications", status_code=202, response_model=ChallengeResponse)
@inject
def request_email_verification(
    body: EmailVerificationRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> ChallengeResponse:
    return ChallengeResponse(
        challenge_id=service.request_email_verification(
            body.orcid, body.email, body.name
        )
    )


@router.post(
    "/email-verifications/{challenge_id}/confirm", response_model=UserIdResponse
)
@inject
def confirm_email_verification(
    challenge_id: str,
    body: CodeRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(
        user_id=service.confirm_email_verification(
            _challenge_id(challenge_id), body.code
        )
    )


@router.post("/challenges/{challenge_id}/resend", status_code=202)
@inject
def resend(
    challenge_id: str,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.resend(_challenge_id(challenge_id))
    return Response(status_code=202)


@router.post("/login", response_model=UserIdResponse)
@inject
def login(
    body: LoginRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> UserIdResponse:
    return UserIdResponse(user_id=service.login(body.email, body.password))


@router.post("/password-reset", status_code=202)
@inject
def request_password_reset(
    body: PasswordResetRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.request_password_reset(body.email)
    return Response(status_code=202)


@router.post("/password-reset/confirm", status_code=204)
@inject
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    service: AccountService = Depends(Provide[Container.account_service]),
) -> Response:
    service.confirm_password_reset(body.token, body.password)
    return Response(status_code=204)
