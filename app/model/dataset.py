from dataclasses import dataclass, field
from datetime import datetime
import enum
from uuid import UUID

from app.model.doi import DOI


class DesignState(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


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
    # TODO: deprecate files in favor to files_in
    files: list[DataFile] = field(default_factory=lambda: [])
    files_in: list[DataFile] = field(default_factory=lambda: [])
    doi: DOI = None


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
    design_state: str = None
