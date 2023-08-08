import logging
from app.models.users import Providers, Roles, Users
from app.repositories.users import UsersRepository
from werkzeug.exceptions import NotFound
from app.controllers.interceptors.authorization import enforcer

repository = UsersRepository()

class UsersService:
    def fetch_by_id(self, id, is_enabled=True):
        return repository.fetch_by_id(id, is_enabled)
    
    def fetch_by_email(self, email, is_enabled=True):
        return repository.fetch_by_email(email, is_enabled)
    
    def fetch_all(self):
        return repository.fetch_all()

    def create(self, request_body):
        try:
            user = Users(name=request_body['name'],
                         email=request_body['email'])
            user.providers.append(Providers(name=request_body['provider']))
            
            user_id = repository.upsert(user).id

            for role in request_body['roles']:
                enforcer.add_role_for_user(user.id, role)
            return user_id
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
                enforcer.add_role_for_user(id, role)
        except Exception as e:
            logging.error(e)
            raise e
        
    def remove_roles(self, id, roles):
        try:
            user = repository.fetch_by_id(id)
            if (user is None):
                raise NotFound(f'User {id} not found')
            for role in roles:
                enforcer.delete_role_for_user(id, role)
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

    def disable(self, id):
        try:
            user = repository.fetch_by_id(id)
            if (user is None):
                raise NotFound(f'User {id} not found')
            user.is_enabled = False
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e

    def enable(self, id):
        try:
            user = repository.fetch_by_id(id)
            if (user is None):
                raise NotFound(f'User {id} not found')
            user.is_enabled = True
            repository.upsert(user)
        except Exception as e:
            logging.error(e)
            raise e
