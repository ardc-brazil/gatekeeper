import logging
from app.models.clients import Clients
from app.repositories.clients import ClientsRepository
from app.services.secrets import hash_password

repository = ClientsRepository()

class ClientsService:
    def __adapt_client(self, client):
        return {"name": client.name, 
                "key": client.key,
                "is_enabled": client.is_enabled,
                "secret": client.secret}

    def fetch(self, api_key):
        res = repository.fetch(api_key)
        if res is not None:
            client = self.__adapt_client(res)
            return client
        
        return None
    
    def fetch_all(self):
        res = repository.fetch_all()
        if res is not None:
            clients = [self.__adapt_client(client) for client in res]
            return clients
    
        return []
    
    def create(self, request_body):
        try:
            client = Clients(name=request_body['name'], 
                             secret=hash_password(request_body['secret']),
                             is_enabled=True)
            repository.upsert(client)
        except Exception as e:
            logging.error(e)
            raise Exception('An error occurred while creating the client')
        
    def update(self, key, request_body):
        try:
            client = repository.fetch(key)
            if client is None:
                raise Exception('Client not found')
            
            client.name = request_body['name']
            client.secret = hash_password(request_body['secret'])

            repository.upsert(client)
        except Exception as e:
            logging.error(e)
            raise Exception('An error occurred while updating the client')
    
    def disable(self, api_key):
        try:
            client = self.fetch(api_key)
            if client is None:
                raise Exception('Client not found')
            client['is_enabled'] = False
            repository.upsert(client)
        except Exception as e:
            logging.error(e)
            raise Exception('An error occurred while disabling the client')