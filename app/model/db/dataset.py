import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import (
    Index,
    Enum,
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from app.model.dataset import DesignState


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    name = Column(String(256), nullable=False)
    data = Column(JSONB, nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    tenancy = Column(String(256), nullable=True)
    design_state = Column(Enum(DesignState), nullable=True)

    versions = relationship("DatasetVersion", lazy="subquery", backref="dataset")

    __table_args__ = (Index("idx_is_enabled", "is_enabled"), Index("idx_name", "name"))


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    name = Column(String(256), nullable=False)
    description = Column(String(256), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=True)
    design_state = Column(Enum(DesignState), nullable=True)
    doi_identifier = Column(String(256), nullable=True)
    doi_state = Column(String(256), nullable=True)

    files = relationship("DataFile", lazy="subquery", backref="dataset_version")
    doi = relationship("DOI", lazy="subquery", backref="dataset_version")

    __table_args__ = (
        Index("idx_dataset_versions_name", "name"),
        Index("idx_dataset_versions_created_at", "created_at"),
        UniqueConstraint('name', 'dataset_id', name='uc_dataset_versions_name_dataset_id')
    )


class DataFile(Base):
    __tablename__ = "data_files"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()"),
    )
    name = Column(String(1024), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    extension = Column(String(64), nullable=True)
    format = Column(String(64), nullable=True)
    storage_file_name = Column(String(1024), nullable=True)
    storage_path = Column(String(2048), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    version_id = Column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False
    )

    __table_args__ = (
        Index("idx_data_files_name", "name"),
        Index("idx_data_files_created_at", "created_at"),
    )
