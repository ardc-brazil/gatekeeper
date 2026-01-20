from dataclasses import dataclass, field
from datetime import datetime
import enum
from uuid import UUID

from app.model.doi import DOI


class DesignState(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class VisibilityStatus(enum.Enum):
    """
    Determines the visibility status of a Dataset.
    """

    # Only authenticated and authorized users can access it
    PRIVATE = 1
    # Dataset metadata is disclosed for public access
    PUBLIC = 2


class FileCollocationStatus(enum.Enum):
    """
    Determines the file collocation status of a Dataset.
    """

    # Files need to be moved from staged/legacy to the new structure
    PENDING = "pending"
    # Files are currently being processed by the archivist worker
    PROCESSING = "processing"
    # All files have been moved to the new structure
    COMPLETED = "completed"


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
    files_size_in_bytes: int = None
    files_count: int = None
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
    visibility: VisibilityStatus = None
    file_collocation_status: FileCollocationStatus = None
    versions: list[DatasetVersion] = field(default_factory=lambda: [])
    current_version: DatasetVersion = None
    version: DatasetVersion = None
    created_at: datetime = None
    updated_at: datetime = None
    file_size_in_bytes: int = None
    file_count: int = None


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
    visibility: str = None
    minimal: bool = False
    page: int = 1
    page_size: int = 10


@dataclass
class PaginatedResult:
    """Result container for paginated queries."""

    items: list
    total_count: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total_count + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
