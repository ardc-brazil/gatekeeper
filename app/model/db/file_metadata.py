import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import (
    Index,
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    BigInteger,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class FileMetadata(Base):
    __tablename__ = "file_metadata"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    data_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_count = Column(BigInteger, nullable=False)
    sample_file_path = Column(String(2048), nullable=True)
    extracted_at = Column(DateTime(timezone=True), nullable=False)
    extractor_version = Column(String(50), nullable=False)
    llm_provider = Column(String(100), nullable=True)

    columns = relationship(
        "ColumnMetadata",
        lazy="subquery",
        backref="file_metadata",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_file_metadata_data_file_id", "data_file_id"),
        UniqueConstraint("data_file_id", name="uc_file_metadata_data_file_id"),
    )


class ColumnMetadata(Base):
    __tablename__ = "column_metadata"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    file_metadata_id = Column(
        UUID(as_uuid=True),
        ForeignKey("file_metadata.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(512), nullable=False)
    dtype = Column(String(50), nullable=False)
    position = Column(Integer, nullable=False)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    mean_value = Column(Float, nullable=True)
    std_value = Column(Float, nullable=True)
    null_count = Column(BigInteger, default=0)
    sample_values = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_column_metadata_file_metadata_id", "file_metadata_id"),
    )
