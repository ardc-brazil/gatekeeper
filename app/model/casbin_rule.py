from app import db
from casbin_sqlalchemy_adapter import CasbinRule as CasbinRuleBase


class CasbinRule(db.Model, CasbinRuleBase):
    id = db.Column(db.Integer, primary_key=True)
