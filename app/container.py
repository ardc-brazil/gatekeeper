import logging
from dependency_injector import containers, providers
import os
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from casbin import SyncedEnforcer

from app.repository.dataset import DatasetRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.repository.user import UserRepository

from app.service.dataset import DatasetService
from app.service.tus import TusService
from app.service.user import UserService

from app.repository.tenancy import TenancyRepository
from app.service.tenancy import TenancyService
from app.service.auth import AuthService
from app.database import Database
from app.repository.client import ClientRepository
from app.service.client import ClientService

logger = logging.getLogger("uvicorn")


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.controller.v1.client.client",
            "app.controller.v1.dataset.dataset",
            "app.controller.v1.dataset.dataset_filter",
            "app.controller.v1.user.user",
            "app.controller.v1.tenancy.tenancy",
            #  "app.controller.v1.tus.tus",
        ]
    )

    env_name = os.getenv("ENV", "local")
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

    tenancy_repository = providers.Factory(
        TenancyRepository,
        session_factory=db.provided.session,
    )

    tenancy_service = providers.Factory(
        TenancyService,
        repository=tenancy_repository,
    )

    casbin_adapter = providers.Singleton(
        CasbinSQLAlchemyAdapter, db.provided.get_engine.call()
    )
    casbin_enforcer = providers.Singleton(
        SyncedEnforcer,
        config.casbin.model_file,
        casbin_adapter,
    )

    user_repository = providers.Factory(
        UserRepository,
        session_factory=db.provided.session,
    )

    user_service = providers.Factory(
        UserService,
        repository=user_repository,
        tenancy_repository=tenancy_repository,
        casbin_enforcer=casbin_enforcer,
    )

    auth_service = providers.Factory(
        AuthService,
        client_service=client_service,
        casbin_enforcer=casbin_enforcer,
    )

    dataset_repository = providers.Factory(
        DatasetRepository,
        session_factory=db.provided.session,
    )

    dataset_version_repository = providers.Factory(
        DatasetVersionRepository,
        session_factory=db.provided.session,
    )

    dataset_service = providers.Factory(
        DatasetService,
        repository=dataset_repository,
        version_repository=dataset_version_repository,
        user_service=user_service,
    )

    tus_service = providers.Factory(
        TusService,
        dataset_service=dataset_service,
    )
