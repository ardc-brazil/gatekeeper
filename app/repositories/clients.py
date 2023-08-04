from methodtools import lru_cache
from app.models.clients import Clients

class ClientsRepository:
    @lru_cache
    def fetch(self, api_key):
        return Clients.query.filter_by(key=api_key).first()