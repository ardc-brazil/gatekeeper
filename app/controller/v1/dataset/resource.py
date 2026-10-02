from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, StrictBool


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


class VersionFilesSummaryResponse(BaseModel):
    count: int = Field(..., title="Number of files")
    total_size_bytes: int = Field(..., title="Total size of the files in bytes")


class EmbargoResponse(BaseModel):
    until: datetime = Field(..., title="Embargo end")
    active: bool = Field(..., title="Whether the embargo is in force now")
    metadata_visible: bool = Field(..., title="Open mode (true) or hidden mode")
    note: Optional[str] = Field(None, title="Note")


class OwnerResponse(BaseModel):
    id: UUID = Field(..., title="Owner's user id")
    name: str = Field(..., title="Owner's name")


class AccessResponse(BaseModel):
    level: str = Field(..., title="owner, write, read or tenancy")
    can_edit: bool = Field(..., title="May change the dataset")
    can_share: bool = Field(..., title="May manage sharing and anonymous links")
    can_manage_embargo: bool = Field(..., title="May set, end or switch the embargo")
    can_extend_embargo: bool = Field(..., title="May extend the embargo")
    can_delete: bool = Field(..., title="May delete the dataset")


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
    files_withheld: bool = Field(False, title="File list withheld by the embargo")
    files_summary: Optional[VersionFilesSummaryResponse] = Field(
        None, title="File count and size"
    )


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
    embargo: Optional[EmbargoResponse] = Field(None, title="Embargo")
    access: Optional[AccessResponse] = Field(None, title="What the caller may do")
    owner: Optional[OwnerResponse] = Field(None, title="Owner")


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
    embargo: Optional[EmbargoResponse] = Field(None, title="Embargo")
    access: Optional[AccessResponse] = Field(None, title="What the caller may do")
    owner: Optional[OwnerResponse] = Field(None, title="Owner")


class PagedDatasetGetResponse(BaseModel):
    content: list[DatasetGetResponse] = Field(..., title="List of data content")
    size: int = Field(
        ..., title="The size of the content (deprecated, use total_count)"
    )
    page: int = Field(1, title="Current page number")
    page_size: int = Field(10, title="Number of items per page")
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
    end_embargo: bool = Field(
        False, title="Confirm that a manual DOI ends the dataset's embargo"
    )


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


class EmbargoSetRequest(BaseModel):
    until: datetime = Field(..., title="Embargo end, at most 90 days ahead")
    metadata_visible: bool = Field(False, title="Open mode (true) or hidden mode")
    note: Optional[str] = Field(None, title="Note", max_length=2000)


class EmbargoExtendRequest(BaseModel):
    until: datetime = Field(..., title="New embargo end, at most 90 days ahead")
    reason: Optional[str] = Field(None, title="Why it is extended", max_length=500)


class EmbargoModeRequest(BaseModel):
    metadata_visible: bool = Field(..., title="Open mode (true) or hidden mode")


class EmbargoStatusResponse(BaseModel):
    embargoed: bool = Field(..., title="Whether the dataset is under embargo now")
    until: Optional[datetime] = Field(None, title="Embargo end")
    doi: Optional[str] = Field(None, title="The version's DOI, while embargoed")


class EmbargoNoteRequest(BaseModel):
    note: Optional[str] = Field(None, title="Note", max_length=2000)


class AccessHistoryUserResponse(BaseModel):
    id: UUID
    name: str


class AccessHistoryEntryResponse(BaseModel):
    event_type: str
    occurred_at: datetime
    actor: Optional[AccessHistoryUserResponse] = None
    subject: Optional[str] = None
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    note: Optional[str] = None


class AccessHistoryResponse(BaseModel):
    items: list[AccessHistoryEntryResponse]


class MembersAccessRequest(BaseModel):
    members_can_edit: StrictBool = Field(
        ..., title="Members of the tenancy may edit (true) or only read (false)"
    )


class MembersAccessResponse(BaseModel):
    members_can_edit: bool = Field(
        ..., title="Members of the tenancy may edit when no embargo is active"
    )
    access: AccessResponse = Field(..., title="What the caller may do")
