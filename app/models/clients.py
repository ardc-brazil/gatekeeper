import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Index
from sqlalchemy.sql import func

from app.services.secrets import hash_password

class Clients(db.Model):
    __tablename__ = 'clients'
    key = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    secret = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def set_secret(self, secret):
        self.secret = hash_password(secret)
