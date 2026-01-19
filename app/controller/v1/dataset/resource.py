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


class DOIResponse(BaseModel):
    identifier: str = Field(..., title="DOI identifier")
    state: str = Field(..., title="State")
    mode: str = Field(..., title="Registration mode. AUTO or MANUAL")


class DatasetVersionResponse(BaseModel):
    id: UUID = Field(..., title="Version ID")
    name: str = Field(..., title="Name")
    design_state: str = Field(..., title="Design state")
    is_enabled: bool = Field(..., title="Is enabled")
    files: list[DataFileResponse] = Field([], title="List of data files")
    files_in: list[DataFileResponse] = Field([], title="List of data files")
    doi: Optional[DOIResponse] = Field(None, title="DOI")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    files_size_in_bytes: int = Field(None, title="Size in bytes of total files")
    files_count: int = Field(None, title="Number of files")


class MinimalDatasetVersionResponse(BaseModel):
    id: UUID = Field(..., title="Version ID")
    name: str = Field(..., title="Name")
    design_state: str = Field(..., title="Design state")
    is_enabled: bool = Field(..., title="Is enabled")
    files_size_in_bytes: int = Field(..., title="Size in bytes of total files")
    files_count: int = Field(..., title="Number of files")
    doi: Optional[DOIResponse] = Field(None, title="DOI")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")


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
    visibility: Optional[str] = Field(None, title="Visibility status")


class MinimalDatasetGetResponse(BaseModel):
    id: UUID = Field(..., title="Dataset ID")
    name: str = Field(..., title="Name")
    # TODO: Maybe `data` should be a str to be compatible with old version
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")
    is_enabled: bool = Field(..., title="Is enabled")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    versions: list[MinimalDatasetVersionResponse] = Field(
        [], title="Version information"
    )
    current_version: Optional[MinimalDatasetVersionResponse] = Field(
        None, title="Current version information"
    )
    design_state: str = Field(..., title="Design state")


class DatasetVersionGetResponse(BaseModel):
    id: UUID = Field(..., title="Dataset ID")
    name: str = Field(..., title="Name")
    # TODO: Maybe `data` should be a str to be compatible with old version
    data: dict = Field(..., title="Dataset information in JSON format")
    tenancy: str = Field(..., title="Tenancy")
    is_enabled: bool = Field(..., title="Is enabled")
    created_at: datetime = Field(..., title="Created at")
    updated_at: datetime = Field(..., title="Updated at")
    version: DatasetVersionResponse = Field(..., title="Specific version information")
    design_state: str = Field(..., title="Design state")
    visibility: Optional[str] = Field(None, title="Visibility status")


class PagedDatasetGetResponse(BaseModel):
    content: list[DatasetGetResponse] = Field(..., title="List of data content")
    size: int = Field(
        ..., title="The size of the content (deprecated, use total_count)"
    )
    page: int = Field(1, title="Current page number")
    page_size: int = Field(20, title="Number of items per page")
    total_count: int = Field(..., title="Total number of matching datasets")
    total_pages: int = Field(..., title="Total number of pages")
    has_next: bool = Field(..., title="Whether there is a next page")
    has_previous: bool = Field(..., title="Whether there is a previous page")


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
    visibility: Optional[str] = Field(None, title="Visibility status")


class DOIErrorResponse(BaseModel):
    code: str = Field(..., title="Error code")
    field: Optional[str] = Field(None, title="Field")


class DOICreateRequest(BaseModel):
    identifier: str = Field(None, title="DOI identifier")
    mode: str = Field(..., title="Mode")


class DOIChangeStateRequest(BaseModel):
    state: str = Field(..., title="State")


class DOIChangeStateResponse(BaseModel):
    new_state: str = Field(None, title="State")


class DOICreateResponse(BaseModel):
    identifier: str = Field(..., title="DOI identifier")
    state: str = Field(None, title="State")
    mode: str = Field(None, title="Registration mode. AUTO or MANUAL")


class DataFileDownloadResponse(BaseModel):
    url: str = Field(..., title="Download URL")


class DatasetVersionCreateRequest(BaseModel):
    datafilesPreviouslyUploaded: list[str] = Field(
        [], title="List of data files ids already created to attach to this version"
    )


class DatasetVersionCreateResponse(BaseModel):
    id: UUID = Field(..., title="Version ID")
    name: str = Field(..., title="Name")
    design_state: str = Field(..., title="Design state")
    is_enabled: bool = Field(..., title="Is enabled")
    files_in: list[DataFileResponse] = Field([], title="List of data files")
    doi: Optional[DOIResponse] = Field(None, title="DOI")


class DatasetVersionInfo(BaseModel):
    """Version information for snapshot responses"""

    id: str = Field(..., title="Version ID")
    name: str = Field(..., title="Version name")
    doi_identifier: Optional[str] = Field(None, title="DOI identifier")
    doi_state: Optional[str] = Field(None, title="DOI state")
    created_at: Optional[str] = Field(None, title="Created at ISO format")


class FileExtensionSummary(BaseModel):
    """Summary of files by extension"""

    extension: str = Field(..., title="File extension (e.g., '.csv', '.json')")
    count: int = Field(..., title="Number of files with this extension")
    total_size_bytes: int = Field(..., title="Total size in bytes for this extension")


class FilesSummary(BaseModel):
    """Summary of dataset files"""

    total_files: int = Field(..., title="Total number of files")
    total_size_bytes: int = Field(..., title="Total size of all files in bytes")
    extensions_breakdown: list[FileExtensionSummary] = Field(
        ..., title="Breakdown by file extension"
    )


class DatasetSnapshotResponse(BaseModel):
    """Response for specific version snapshot"""

    dataset_id: str = Field(..., title="Dataset ID")
    name: str = Field(..., title="Dataset name")
    version_name: str = Field(..., title="Version name")
    doi_identifier: Optional[str] = Field(None, title="DOI identifier")
    doi_link: Optional[str] = Field(None, title="DOI URL link")
    doi_state: Optional[str] = Field(None, title="DOI state")
    publication_date: Optional[str] = Field(None, title="Publication date ISO format")
    files_summary: FilesSummary = Field(..., title="Summary of dataset files")
    data: dict = Field(..., title="Dataset metadata (untyped)")


class DatasetLatestSnapshotResponse(BaseModel):
    """Response for latest snapshot with versions list"""

    dataset_id: str = Field(..., title="Dataset ID")
    name: str = Field(..., title="Dataset name")
    version_name: str = Field(..., title="Version name")
    doi_identifier: Optional[str] = Field(None, title="DOI identifier")
    doi_link: Optional[str] = Field(None, title="DOI URL link")
    doi_state: Optional[str] = Field(None, title="DOI state")
    publication_date: Optional[str] = Field(None, title="Publication date ISO format")
    files_summary: FilesSummary = Field(..., title="Summary of dataset files")
    data: dict = Field(..., title="Dataset metadata (untyped)")
    versions: list[DatasetVersionInfo] = Field(..., title="All published versions")
