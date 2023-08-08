
from app.models.users import Users
from app import db

class UsersRepository:
    def fetch_by_id(self, id, is_enabled=True):
        return Users.query.filter_by(id=id, is_enabled=is_enabled).first()
    
    def fetch_by_email(self, email, is_enabled=True):
        return Users.query.filter_by(email=email, is_enabled=is_enabled).first()
    
    def fetch_all(self):
        return Users.query.all()

    def upsert(self, user):
        if (user.id is None):
            db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user
