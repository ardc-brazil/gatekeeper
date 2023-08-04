from methodtools import lru_cache
from app.models.clients import Clients
from app import db

class ClientsRepository:
    # @lru_cache
    def fetch(self, api_key, is_enabled=True):
        return Clients.query.filter_by(key=api_key, is_enabled=is_enabled).first()
    
    def fetch_all(self, is_enabled=True):
        return Clients.query.filter_by(is_enabled=is_enabled).all()
    
    def upsert(self, client):
        if (client.key is None):
            db.session.add(client)
        db.session.commit()
        db.session.refresh(client)
        return client
    