from pydantic import BaseModel, Field


class TenancyGetResponse(BaseModel):
    name: str = Field(..., description="Tenancy name")
    is_enabled: bool = Field(..., description="Tenancy enabled status")


class TenancyUpdateRequest(BaseModel):
    name: str = Field(..., description="Tenancy name")
    is_enabled: bool = Field(..., description="Tenancy enabled status")


class TenancyCreateRequest(BaseModel):
    name: str = Field(..., description="Tenancy name")
    is_enabled: bool = Field(..., description="Tenancy enabled status")
