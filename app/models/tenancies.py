from app import db
from sqlalchemy.sql import func


class Tenancies(db.Model):
    __tablename__ = "tenancies"
    name = db.Column(db.String(256), primary_key=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
