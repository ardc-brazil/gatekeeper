from app import db
from casbin_sqlalchemy_adapter import CasbinRule


class CasbinRules(db.Model, CasbinRule):
    id = db.Column(db.Integer, primary_key=True)
