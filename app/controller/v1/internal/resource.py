from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class DataFileCollocationResponse(BaseModel):
    """Response model for DataFile in collocation context."""

    id: UUID = Field(..., title="File ID")
    name: str = Field(..., title="File name")
    size_bytes: int = Field(..., title="Size in bytes")
    storage_path: str = Field(..., title="Current storage path in MinIO")
    storage_file_name: str = Field(..., title="Storage file name (UUID)")
    extension: Optional[str] = Field(None, title="File extension")
    format: Optional[str] = Field(None, title="File format")
    created_at: datetime = Field(..., title="Created at")
    created_by: Optional[UUID] = Field(None, title="User ID who uploaded the file")


class DatasetPendingCollocationResponse(BaseModel):
    """Response model for datasets pending file collocation."""

    id: UUID = Field(..., title="Dataset ID")
    name: str = Field(..., title="Dataset name")
    created_at: datetime = Field(..., title="Created at")
    file_collocation_status: Optional[str] = Field(
        None, title="File collocation status"
    )
    file_count: int = Field(0, title="Number of files in dataset")


class UpdateFilePathRequest(BaseModel):
    """Request model to update a file's storage path."""

    storage_path: str = Field(
        ..., title="New storage path", min_length=1, max_length=2048
    )


class UpdateCollocationStatusRequest(BaseModel):
    """Request model to update dataset's file collocation status."""

    status: str = Field(..., title="New status (PENDING, PROCESSING, COMPLETED)")
