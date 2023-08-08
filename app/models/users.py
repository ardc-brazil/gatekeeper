import sqlalchemy
from app import db
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

user_provider_association = db.Table('user_provider',
    db.Column('user_id', UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True),
    db.Column('provider_id', db.Integer, db.ForeignKey('providers.id'), primary_key=True)
)

user_roles_association = db.Table('user_roles',
    db.Column('user_id', UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

class Users(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()"))
    name = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(256), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    providers = relationship('Provider', secondary=user_provider_association, backref='users')
    roles = relationship('Role', secondary=user_roles_association, backref='users')

    __table_args__ = (Index('idx_users_email', email, unique=True),)

class Providers(db.Model):
    __tablename__ = 'providers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)

class Roles(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
