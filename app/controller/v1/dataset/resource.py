from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class DataFileResponse(BaseModel):
    id: UUID = Field(..., title="File ID")
    name: str = Field(..., title="Name")
    size_bytes: int = Field(..., title="Size in bytes")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    extension: Optional[str] = Field(None, title="Extension")
    format: Optional[str] = Field(None, title="Format")
    storage_file_name: Optional[str] = Field(None, title="Storage file name")
    storage_path: Optional[str] = Field(None, title="Storage path")
    created_by: Optional[UUID] = Field(None, title="Created by")

class DatasetVersionResponse(BaseModel):
    id: UUID = Field(..., title="Version ID")
    name: str = Field(..., title="Name")
    design_state: str = Field(..., title="Design state")
    is_enabled: bool = Field(..., title="Is enabled")
    files: list[DataFileResponse] = Field([], title="List of data files")

class DatasetGetResponse(BaseModel):
    id: UUID = Field(..., title="Dataset ID")
    name: str = Field(..., title="Name")
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")
    is_enabled: bool = Field(..., title="Is enabled")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    versions: list[DatasetVersionResponse] = Field([], title="Version information")
    current_version: Optional[DatasetVersionResponse] = Field(None, title="Current version information")

class DatasetUpdateRequest(BaseModel):
    name: str = Field(..., title="Name")
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")

class DatasetCreateRequest(BaseModel):
    name: str = Field(..., title="Name")
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")

class DatasetCreateResponse(BaseModel):
    id: UUID = Field(..., title="Dataset ID")
    design_state: str = Field(..., title="Design state")
    versions: list[DatasetVersionResponse] = Field(..., title="Version information")
