import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID
from casbin_sqlalchemy_adapter import CasbinRule

class CasbinRules(db.Model, CasbinRule):
    __tablename__ = 'casbin_rules'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
