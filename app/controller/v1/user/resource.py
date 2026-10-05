from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class UserProvider(BaseModel):
    name: str = Field(..., description="Provider name")
    reference: str = Field(..., description="Provider reference")


class UserGetResponse(BaseModel):
    id: UUID = Field(..., description="User id")
    name: str = Field(..., description="User name")
    email: str | None = Field(None, description="User email")
    roles: list[str] = Field(..., description="User roles")
    is_enabled: bool = Field(..., description="User enabled status")
    created_at: datetime = Field(..., description="User created time")
    updated_at: datetime = Field(..., description="User updated time")
    providers: list[UserProvider] = Field(..., description="User providers")
    tenancies: list[str] = Field(..., description="User tenancies")
    email_verified_at: datetime | None = Field(
        None, description="When the email was confirmed; null if it never was"
    )
    has_password: bool = Field(
        False, description="Whether the account can sign in with a password"
    )


class UserUpdateRequest(BaseModel):
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")


class UserCreateRequest(BaseModel):
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")
    providers: list[UserProvider] = Field([], description="User providers")
    roles: list[str] = Field([], description="User roles")


class UserCreateResponse(BaseModel):
    id: UUID = Field(..., description="User id")


class UserProviderAddRequest(BaseModel):
    name: str = Field(..., description="Provider name")
    reference: str = Field(..., description="Provider reference")


class UserTenanciesRequest(BaseModel):
    tenancies: list[str] = Field([], description="Tenancies name")


class UserEnforceRequest(BaseModel):
    resource: str = Field(..., description="Resource name")
    action: str = Field(..., description="Action name")


class UserEnforceResponse(BaseModel):
    allow: bool = Field(..., description="Allow access")


class UserPasswordChangeRequest(BaseModel):
    current_password: str = Field(..., description="The account's current password")
    new_password: str = Field(..., description="New password, 10 to 128 characters")
