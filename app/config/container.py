from logging import Logger
from dependency_injector import containers, providers
from app.services.infrastructure import InfrastructureService
from app.services.other_service import OtherService

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=['app.controllers.v1.infrastructure'])

    config = providers.Configuration()
    
    other_service = providers.Factory(OtherService)

    infrastructure_service = providers.Factory(InfrastructureService, other_service=other_service)
