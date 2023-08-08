
from app.models.users import Users
from app import db

class UsersRepository:
    def fetch_by_id(self, id):
        return Users.query.filter_by(id=id).first()
    
    def fetch_by_email(self, email):
        return Users.query.filter_by(email=email).first()
    
    def upsert(self, user):
        if (user.key is None):
            db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user
