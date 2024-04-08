import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

dataset_version_association = db.Table('dataset_version',
    db.Column('dataset_id', UUID(as_uuid=True), db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('version_id', UUID(as_uuid=True), db.ForeignKey('dataset_versions.id'), primary_key=True)
)

dataset_files_association = db.Table('dataset_file',
    db.Column('dataset_id', UUID(as_uuid=True), db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('file_id', UUID(as_uuid=True), db.ForeignKey('data_files.id'), primary_key=True)                               
)

class Datasets(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(256), nullable=False)
    data = db.Column(JSONB, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    owner_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    tenancy = db.Column(db.String(256), nullable=True)

    versions = relationship('DatasetVersions', secondary=dataset_version_association, backref='datasets')
    files = relationship('DataFiles', secondary=dataset_files_association, backref='datasets')

    __table_args__ = (Index('idx_is_enabled', 'is_enabled'),
                      Index('idx_name', 'name'))

class DatasetVersions(db.Model):
    __tablename__ = 'dataset_versions'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(256), nullable=False)
    description = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    author_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (Index('idx_dataset_versions_name', 'name'),
                      Index('idx_dataset_versions_created_at', 'created_at'))

class DataFiles(db.Model):
    __tablename__ = 'data_files'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(1024), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    extension = db.Column(db.String(64), nullable=True)
    format = db.Column(db.String(64), nullable=True)
    storage_file_name = db.Column(db.String(1024), nullable=True)
    storage_path = db.Column(db.String(2048), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    author_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)

    __table_args__ = (Index('idx_data_files_name', 'name'),
                      Index('idx_data_files_created_at', 'created_at'))
