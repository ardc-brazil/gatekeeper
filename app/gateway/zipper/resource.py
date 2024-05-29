from uuid import UUID
from pydantic import BaseModel, Field


class CreateZipRequest(BaseModel):
    files: list[str] = Field(..., title="List of file names to be zipped")
    bucket: str = Field(..., title="Name of the bucket")
    zip_name: str | None = Field(None, title="Name of the zip file")


class CreateZipResponse(BaseModel):
    id: UUID = Field(..., title="Zip ID")
    status: str = Field(..., title="Zip status")
    name: str | None = Field(None, title="Name of the zip file")
