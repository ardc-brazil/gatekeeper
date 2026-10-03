from uuid import UUID

from pydantic import BaseModel, Field


class SignUpRequest(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address; the account's identity")
    password: str = Field(..., description="10 to 128 characters")


class EmailVerificationRequest(BaseModel):
    orcid: str = Field(..., description="ORCID iD of the signed-in ORCID session")
    email: str = Field(..., description="Email address to confirm")
    name: str = Field(..., description="Name given by ORCID")


class CodeRequest(BaseModel):
    code: str = Field(..., description="The 6-digit code from the email")


class LoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")


class PasswordResetRequest(BaseModel):
    email: str = Field(..., description="Email address of the account")


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., description="Token from the reset link")
    password: str = Field(..., description="New password, 10 to 128 characters")


class ChallengeResponse(BaseModel):
    challenge_id: UUID = Field(..., description="Challenge to confirm or resend")


class UserIdResponse(BaseModel):
    user_id: UUID = Field(..., description="Gatekeeper user id")
