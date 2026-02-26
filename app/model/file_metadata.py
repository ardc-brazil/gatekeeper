"""Domain models for file metadata."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class ColumnMetadata:
    """Metadata for a single column."""

    name: str
    dtype: str  # float, int, datetime, string
    position: int
    file_metadata_id: UUID | None = None
    id: UUID | None = None
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    std_value: float | None = None
    null_count: int = 0
    sample_values: list[str] = field(default_factory=list)
    description: str | None = None


@dataclass
class FileMetadata:
    """File-level metadata."""

    data_file_id: UUID
    row_count: int
    extracted_at: datetime
    extractor_version: str
    id: UUID | None = None
    sample_file_path: str | None = None
    llm_provider: str | None = None
    columns: list[ColumnMetadata] = field(default_factory=list)
