from app.model.user import Provider, User, user_provider_association
from app import db
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import true


class UserRepository:
    def fetch_by_id(self, id, is_enabled=True):
        return User.query.filter_by(id=id, is_enabled=is_enabled).first()

    def fetch_by_email(self, email, is_enabled=True):
        return User.query.filter_by(email=email, is_enabled=is_enabled).first()

    def fetch_by_provider(self, provider_name, reference, is_enabled=True):
        provider_alias = aliased(Provider)

        user = (
            db.session.query(User)
            .join(user_provider_association)
            .join(
                provider_alias,
                provider_alias.id == user_provider_association.c.provider_id,
            )
            .filter(
                provider_alias.name == provider_name,
                Provider.reference == reference,
                User.is_enabled == is_enabled,
            )
            .first()
        )

        return user

    def upsert(self, user):
        if user.id is None:
            db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user

    def search(self, query_params):
        query = db.session.query(User)

        if query_params["email"]:
            query = query.filter(User.email == query_params["email"])

        if query_params["is_enabled"]:
            query = query.filter(User.is_enabled == query_params["is_enabled"])
        else:
            query = query.filter(User.is_enabled == true())

        return query.all()
