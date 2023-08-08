import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Index
from sqlalchemy.sql import func

class Datasets(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(256), nullable=False)
    data = db.Column(JSONB, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    owner_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)

    __table_args__ = (Index('idx_is_enabled', 'is_enabled'),
                      Index('idx_name', 'name'))
