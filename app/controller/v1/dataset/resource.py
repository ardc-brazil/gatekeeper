from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.model.doi import DOI, Mode as DOIMode, State as DOIState


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
    doi: Optional[DOI] = Field(None, title="DOI")


class DatasetGetResponse(BaseModel):
    id: UUID = Field(..., title="Dataset ID")
    name: str = Field(..., title="Name")
    # TODO: Maybe `data` should be a str to be compatible with old version
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")
    is_enabled: bool = Field(..., title="Is enabled")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    versions: list[DatasetVersionResponse] = Field([], title="Version information")
    current_version: Optional[DatasetVersionResponse] = Field(
        None, title="Current version information"
    )
    design_state: str = Field(..., title="Design state")


class PagedDatasetGetResponse(BaseModel):
    content: list[DatasetGetResponse] = Field(..., title="List of data content")
    size: int = Field(..., title="The size of the content")


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
    name: str = Field(..., title="Dataset title")
    data: dict = Field(..., title="Dataset information in JSON format")
    design_state: str = Field(..., title="Design state")
    tenancy: str = Field(..., title="Tenancy")
    versions: list[DatasetVersionResponse] = Field(..., title="Version information")
    current_version: DatasetVersionResponse = Field(
        None, title="Current version information"
    )

class DOIErrorResponse(BaseModel):
    code: str = Field(..., title="Error code")
    field: Optional[str] = Field(None, title="Field")

class DOICreateRequest(BaseModel):
    identifier: str = Field(..., title="DOI identifier")
    mode: DOIMode = Field(..., title="Mode")

class DOIChangeStateRequest(BaseModel):
    state: DOIState = Field(..., title="State")

class DOIResponse(BaseModel):
    identifier: str = Field(..., title="DOI identifier")
    state: DOIState = Field(..., title="State")

class DOIChangeStateResponse(BaseModel):
    new_state: DOIState = Field(None, title="State")
    errors: list[DOIErrorResponse] = Field(None, title="List of errors")

class DOICreateResponse(BaseModel):
    identifier: str = Field(..., title="DOI identifier")
    state: DOIState = Field(None, title="State")
    