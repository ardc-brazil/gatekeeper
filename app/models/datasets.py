import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB

class Datasets(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(256), nullable=False)
    data = db.Column(JSONB, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
