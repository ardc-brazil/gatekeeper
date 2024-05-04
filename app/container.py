import logging
from dependency_injector import containers, providers
from minio import Minio
import os

from repository.tenancy import TenancyRepository
from service.tenancy import TenancyService
from service.auth import AuthService
from database import Database
from repository.client import ClientRepository
from service.client import ClientService

logger = logging.getLogger("uvicorn")


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=["controllers.v1.clients.clients",
                #  "app.controllers.v1.datasets.datasets",
                #  "app.controllers.v1.users.users",
                 "controllers.v1.tenancies.tenancies",
                #  "app.controllers.v1.tus.tus",
                 ]
    )

    env_name = os.getenv("ENV", "local")
    import os
    print(os.getcwd())
    # TODO fix this path
    config_file = f"./{env_name}_config.yml"
    logger.info(f"Using config file: {config_file}")
    config = providers.Configuration(yaml_files=[config_file])

    db = providers.Singleton(Database, db_url=config.db.url)

    client_repository = providers.Factory(
        ClientRepository,
        session_factory=db.provided.session,
    )
    
    client_service = providers.Factory(
        ClientService,
        repository=client_repository,
    )

    auth_service = providers.Factory(
        AuthService,
        client_service=client_service,
    )

    tenancy_repository = providers.Factory(
        TenancyRepository,
        session_factory=db.provided.session,
    )

    tenancy_service = providers.Factory(
        TenancyService,
        repository=tenancy_repository,
    )

