from http.client import HTTPException
import json

from flask import Blueprint
from app.models import Users

bp = Blueprint('routes', __name__)

@bp.route('/')
def hello():
    return 'Hello, World!'

@bp.route('/users')
def users():
    users = Users.query.all()
    return {'users': [user.name for user in users]}
