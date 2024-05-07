from uuid import UUID
from pydantic import BaseModel, Field


class ClientGetResponse(BaseModel):
    key: UUID = Field(..., description="Client key")
    name: str = Field(..., description="Client name")
    is_enabled: bool = Field(..., description="Client enabled status")


class ClientUpdateRequest(BaseModel):
    name: str | None = Field(None, description="Client name")
    secret: str | None = Field(None, description="Client secret")


class ClientCreateRequest(BaseModel):
    name: str = Field(..., description="Client name")
    secret: str = Field(..., description="Client secret")


class ClientCreateResponse(BaseModel):
    key: UUID = Field(..., description="Client key")
