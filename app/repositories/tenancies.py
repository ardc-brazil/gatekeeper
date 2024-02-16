from app.models.tenancies import Tenancies
from app import db

class TenancyRepository:
    def fetch(self, tenancy, is_enabled=True):
        return Tenancies.query.filter_by(name=tenancy, is_enabled=is_enabled).first()
    
    def fetch_all(self, is_enabled=None):
        if is_enabled:
            return Tenancies.query.filter_by(is_enabled=is_enabled).all()
        return Tenancies.query.all()
    
    def upsert(self, tenancy):
        exists = self.fetch(tenancy.name)
        if not exists:
            db.session.add(tenancy)
        db.session.commit()
        db.session.refresh(tenancy)
        return tenancy
