import logging
from app.models.users import Users
from app.repositories.users import UsersRepository
from werkzeug.exceptions import NotFound

repository = UsersRepository()

class UsersService:
    def fetch_by_id(self, id, is_enabled=True):
        return repository.fetch_by_id(id, is_enabled)
    
    def fetch_by_email(self, email, is_enabled=True):
        return repository.fetch_by_email(email, is_enabled)
    
    def create(self, request_body):
        try:
            user = Users(name=request_body['name'],
                         email=request_body['email'])
            user.providers.append(request_body['provider'])
            roles = request_body['role'].split(',')
            for role in roles:
                user.roles.append(role)
            
            return repository.upsert(user).id
        except Exception as e:
            logging.error(e)
            raise e
    
    def update(self, id, request_body):
        try: 
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f'User {id} not found')
            user.name = request_body['name']
            user.email = request_body['email']
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
    
    def add_roles(self, id, roles):
        try:
            user = repository.fetch_by_id(id)
            if user is None:
                raise NotFound(f'User {id} not found')
            for role in roles:
                user.roles.append(role)
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
        
    def remove_roles(self, id, roles):
        try:
            user = repository.fetch_by_id(id)
            if (user is None):
                raise NotFound(f'User {id} not found')
            for role in roles:
                user.roles.remove(role)
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
    
    def add_provider(self, id, provider):
        try:
            user = repository.fetch_by_id(id)
            if (user is None):
                raise NotFound(f'User {id} not found')
            user.providers.append(provider)
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
