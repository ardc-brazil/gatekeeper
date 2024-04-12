import logging
from app.exceptions.UnauthorizedException import UnauthorizedException
from app.services.clients import ClientsService
from app.services.secrets import check_password

client_service = ClientsService()

class AuthenticationService:
    def authenticate_client(self, api_key: str, salted_api_secret: str):
        if (api_key is None or salted_api_secret is None):
            raise UnauthorizedException('missing_information')
    
        client = client_service.fetch(api_key)

        if (client is None):
            logging.info(f'api_key {api_key} not found')
            raise UnauthorizedException('wrong_credentials')
        
        if not check_password(salted_api_secret, client['secret']):
            logging.warn(f'incorrect api_secret {salted_api_secret}')
            raise UnauthorizedException('wrong_credentials')
