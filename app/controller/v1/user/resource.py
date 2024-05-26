from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class UserProvider(BaseModel):
    name: str = Field(..., description="Provider name")
    reference: str = Field(..., description="Provider reference")


class UserGetResponse(BaseModel):
    id: UUID = Field(..., description="User id")
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")
    roles: list[str] = Field(..., description="User roles")
    is_enabled: bool = Field(..., description="User enabled status")
    created_at: datetime = Field(..., description="User created time")
    updated_at: datetime = Field(..., description="User updated time")
    providers: list[UserProvider] = Field(..., description="User providers")
    tenancies: list[str] = Field(..., description="User tenancies")


class UserUpdateRequest(BaseModel):
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")


class UserCreateRequest(BaseModel):
    name: str = Field(..., description="User name")
    email: str = Field(..., description="User email")
    providers: list[UserProvider] = Field([], description="User providers")
    roles: list[str] = Field([], description="User roles")


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
