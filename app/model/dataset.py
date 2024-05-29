from dataclasses import dataclass, field
from datetime import datetime
import enum
from uuid import UUID


class DesignState(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"

class ZipStatus(enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

@dataclass
class DataFile:
    name: str
    size_bytes: int
    created_at: datetime = None
    updated_at: datetime = None
    id: UUID = None
    extension: str = None
    format: str = None
    storage_file_name: str = None
    storage_path: str = None
    created_by: UUID = None


@dataclass
class DatasetVersion:
    name: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
    id: UUID = None
    description: str = None
    created_by: UUID = None
    design_state: DesignState = None
    files: list[DataFile] = field(default_factory=lambda: [])
    zip_id: UUID = None
    zip_status: ZipStatus = None

@dataclass
class Dataset:
    name: str
    data: dict
    id: UUID = None
    is_enabled: bool = None
    owner_id: UUID = None
    tenancy: str = None
    design_state: DesignState = None
    versions: list[DatasetVersion] = field(default_factory=lambda: [])
    current_version: DatasetVersion = None
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class DatasetQuery:
    categories: list[str] = field(default_factory=lambda: [])
    level: str = None
    data_types: list[str] = field(default_factory=lambda: [])
    date_from: datetime = None
    date_to: datetime = None
    full_text: str = None
    include_disabled: bool = False
    version: str = None
