import logging
from dependency_injector import containers, providers
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from casbin import SyncedEnforcer
from minio import Minio

from app.gateway.doi.doi import DOIGateway
from app.gateway.email.smtp import SmtpSender, public_hostname
from app.gateway.object_storage.http_client import build_http_client
from app.service.health import DependencyHealthService
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.repository.access_event import AccessEventRepository
from app.repository.auth_challenge import AuthChallengeRepository
from app.repository.datafile import DataFileRepository
from app.repository.dataset import DatasetRepository
from app.repository.dataset_anonymous_link import DatasetAnonymousLinkRepository
from app.repository.dataset_invitation import DatasetInvitationRepository
from app.repository.dataset_version import DatasetVersionRepository
from app.repository.doi import DOIRepository
from app.repository.email import EmailRepository
from app.repository.embargo_notification import EmbargoNotificationRepository
from app.repository.permission import PermissionRepository
from app.repository.tenancy_event import TenancyEventRepository
from app.repository.tenancy_invitation import TenancyInvitationRepository
from app.repository.tenancy_membership import TenancyMembershipRepository
from app.repository.tenancy_request import TenancyRequestRepository
from app.repository.user import UserRepository

from app.service.account import AccountService
from app.service.anonymous_link import AnonymousLinkService
from app.service.access_history import AccessHistoryService
from app.service.dataset import DatasetService
from app.service.dataset_collocation import DatasetCollocationService
from app.service.dataset_access import DatasetAccessService
from app.service.dataset_access_audit import DatasetAccessAudit
from app.service.doi import DOIService
from app.service.email import EmailService
from app.service.email_template import EmailTemplateRenderer
from app.service.embargo import EmbargoService
from app.service.embargo_termination import EmbargoTermination
from app.service.members_access import MembersAccessService
from app.service.notification import EmbargoNotificationService
from app.service.password import PasswordHasher
from app.service.permission import PermissionService
from app.service.share import ShareService
from app.service.tenancy_admin import TenancyAdminService
from app.service.tenancy_invitation import TenancyInvitationService
from app.service.tenancy_membership import TenancyMembershipService
from app.service.tenancy_notifier import TenancyNotifier
from app.service.tenancy_request import TenancyRequestService
from app.service.tus import TusService
from app.service.user import UserService

from app.repository.tenancy import TenancyRepository
from app.service.tenancy import TenancyService
from app.service.auth import AuthService
from app.database import Database
from app.repository.client import ClientRepository
from app.repository.platform_state import PlatformStateRepository
from app.service.client import ClientService
from app.config import settings

logger = logging.getLogger("uvicorn")


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            # dependency-injector 4.41 injects into a sync @inject dependency
            # only when its own module is wired.
            "app.controller.interceptor.authentication",
            "app.controller.interceptor.authorization",
            "app.controller.v1.auth.auth",
            "app.controller.v1.client.client",
            "app.controller.v1.dataset.dataset",
            "app.controller.v1.dataset.dataset_filter",
            "app.controller.v1.dataset.dataset_snapshot",
            "app.controller.v1.dataset.embargo",
            "app.controller.v1.dataset.embargo_status",
            "app.controller.v1.dataset.members_access",
            "app.controller.v1.dataset.share",
            "app.controller.v1.dataset.anonymous_link",
            "app.controller.v1.invitation.invitation",
            "app.controller.v1.anonymous.anonymous",
            "app.controller.v1.user.user",
            "app.controller.v1.user.tenancy_access",
            "app.controller.v1.tenancy.tenancy",
            "app.controller.v1.tus.tus",
            "app.controller.v1.internal.dataset_collocation",
            "app.controller.v1.internal.notification",
            "app.controller.v1.admin.email",
            "app.controller.v1.admin.tenancy",
            "app.controller.v1.infrastructure.infrastructure",
        ]
    )

    config = providers.Configuration()
    json_config = settings.model_dump()
    config.from_dict(json_config)

    db = providers.Singleton(
        Database,
        db_url=config.DATABASE_URL,
        log_enabled=config.DATABASE_LOG_ENABLED,
    )

    client_repository = providers.Factory(
        ClientRepository,
        session_factory=db.provided.session,
    )

    platform_state_repository = providers.Factory(
        PlatformStateRepository,
        session_factory=db.provided.session,
    )

    # Singleton so the lru_cache on fetch() is shared: as a Factory each request
    # built a new instance, and `self` is part of the cache key.
    client_service = providers.Singleton(
        ClientService,
        repository=client_repository,
        client_secret_pepper=config.AUTH_CLIENT_SECRET_PEPPER,
    )

    tenancy_repository = providers.Factory(
        TenancyRepository,
        session_factory=db.provided.session,
    )

    casbin_adapter = providers.Singleton(
        CasbinSQLAlchemyAdapter, db.provided.get_engine.call()
    )
    casbin_enforcer = providers.Singleton(
        SyncedEnforcer,
        config.CASBIN_MODEL_FILE,
        casbin_adapter,
    )

    email_repository = providers.Factory(
        EmailRepository,
        session_factory=db.provided.session,
    )

    email_renderer = providers.Singleton(
        EmailTemplateRenderer,
        site_url=config.PUBLIC_BASE_URL,
    )

    smtp_sender = providers.Factory(
        SmtpSender,
        host=config.SMTP_HOST,
        port=config.SMTP_PORT,
        username=config.SMTP_USERNAME,
        password=config.SMTP_PASSWORD,
        starttls=config.SMTP_STARTTLS,
        timeout_seconds=config.SMTP_TIMEOUT_SECONDS,
        local_hostname=providers.Callable(public_hostname, config.PUBLIC_BASE_URL),
    )

    email_service = providers.Factory(
        EmailService,
        repository=email_repository,
        renderer=email_renderer,
        sender=smtp_sender,
        enabled=config.EMAIL_ENABLED,
        from_name=config.EMAIL_FROM_NAME,
        from_address=config.EMAIL_FROM_ADDRESS,
        reply_to=config.EMAIL_REPLY_TO,
        template_version=config.BUILD_COMMIT,
    )

    user_repository = providers.Factory(
        UserRepository,
        session_factory=db.provided.session,
    )

    tenancy_event_repository = providers.Factory(
        TenancyEventRepository,
        session_factory=db.provided.session,
    )

    user_service = providers.Factory(
        UserService,
        repository=user_repository,
        tenancy_repository=tenancy_repository,
        casbin_enforcer=casbin_enforcer,
        tenancy_events=tenancy_event_repository,
    )

    tenancy_membership_repository = providers.Factory(
        TenancyMembershipRepository,
        session_factory=db.provided.session,
    )

    tenancy_notifier = providers.Factory(
        TenancyNotifier,
        email_service=email_service,
        admin_emails=config.ADMIN_NOTIFICATION_EMAILS,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    tenancy_membership_service = providers.Factory(
        TenancyMembershipService,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        users=user_repository,
        notifier=tenancy_notifier,
    )

    tenancy_service = providers.Factory(
        TenancyService,
        repository=tenancy_repository,
        membership_service=tenancy_membership_service,
    )

    tenancy_request_repository = providers.Factory(
        TenancyRequestRepository,
        session_factory=db.provided.session,
    )

    tenancy_request_service = providers.Factory(
        TenancyRequestService,
        requests=tenancy_request_repository,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        users=user_repository,
        notifier=tenancy_notifier,
    )

    auth_service = providers.Factory(
        AuthService,
        client_service=client_service,
        casbin_enforcer=casbin_enforcer,
        file_upload_token_secret=config.AUTH_FILE_UPLOAD_TOKEN_SECRET,
        client_secret_pepper=config.AUTH_CLIENT_SECRET_PEPPER,
    )

    doi_gateway = providers.Factory(
        DOIGateway,
        base_url=config.DOI_BASE_URL,
        login=config.DOI_LOGIN,
        password=config.DOI_PASSWORD,
        timeout_seconds=config.DOI_TIMEOUT_SECONDS,
    )

    doi_repository = providers.Factory(
        DOIRepository,
        session_factory=db.provided.session,
    )

    doi_service = providers.Factory(
        DOIService,
        doi_gateway=doi_gateway,
        doi_repository=doi_repository,
        doi_prefix=config.DOI_PREFIX,
    )

    minio_http_client = providers.Factory(
        build_http_client,
        connect_timeout_seconds=config.MINIO_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds=config.MINIO_TIMEOUT_SECONDS,
        retries=config.MINIO_RETRIES,
    )

    minio_client = providers.Factory(
        Minio,
        endpoint=config.MINIO_URL,
        http_client=minio_http_client,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=config.MINIO_USE_SSL,
        # Set a default region to prevent the client from attempting to connect
        # to MinIO to auto-detect the region before generating presigned URLs.
        # For more details, refer to: https://github.com/minio/minio-py/issues/759#issuecomment-490277280
        region=config.MINIO_DEFAULT_REGION_ID,
    )

    minio_gateway = providers.Factory(
        ObjectStorageGateway,
        minio_client=minio_client,
    )

    # A health check reports the state now: no retries, and no long wait on a
    # storage that has stopped answering.
    health_minio_gateway = providers.Factory(
        ObjectStorageGateway,
        minio_client=providers.Factory(
            minio_client,
            http_client=providers.Factory(
                build_http_client,
                connect_timeout_seconds=config.MINIO_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=config.MINIO_CONNECT_TIMEOUT_SECONDS,
                retries=0,
            ),
        ),
    )

    dependency_health_service = providers.Factory(
        DependencyHealthService,
        database=db,
        object_storage=health_minio_gateway,
        bucket=config.MINIO_DATASET_BUCKET,
    )

    dataset_repository = providers.Factory(
        DatasetRepository,
        session_factory=db.provided.session,
    )

    dataset_version_repository = providers.Factory(
        DatasetVersionRepository,
        session_factory=db.provided.session,
    )

    data_file_repository = providers.Factory(
        DataFileRepository,
        session_factory=db.provided.session,
    )

    dataset_collocation_service = providers.Factory(
        DatasetCollocationService,
        dataset_repository=dataset_repository,
        datafile_repository=data_file_repository,
    )

    permission_repository = providers.Factory(
        PermissionRepository,
        session_factory=db.provided.session,
    )

    access_event_repository = providers.Factory(
        AccessEventRepository,
        session_factory=db.provided.session,
    )

    dataset_access_audit = providers.Factory(
        DatasetAccessAudit,
        event_repository=access_event_repository,
    )

    dataset_access_service = providers.Factory(
        DatasetAccessService,
        permission_repository=permission_repository,
        user_service=user_service,
    )

    embargo_termination = providers.Factory(
        EmbargoTermination,
        repository=dataset_repository,
        audit=dataset_access_audit,
    )

    dataset_service = providers.Factory(
        DatasetService,
        repository=dataset_repository,
        version_repository=dataset_version_repository,
        data_file_repository=data_file_repository,
        user_service=user_service,
        doi_service=doi_service,
        minio_gateway=minio_gateway,
        tenancy_service=tenancy_service,
        access_service=dataset_access_service,
        embargo_termination=embargo_termination,
        dataset_bucket=config.MINIO_DATASET_BUCKET,
    )

    embargo_service = providers.Factory(
        EmbargoService,
        dataset_service=dataset_service,
        repository=dataset_repository,
        access_service=dataset_access_service,
        audit=dataset_access_audit,
        termination=embargo_termination,
    )

    members_access_service = providers.Factory(
        MembersAccessService,
        dataset_service=dataset_service,
        repository=dataset_repository,
        access_service=dataset_access_service,
        audit=dataset_access_audit,
    )

    tus_service = providers.Factory(
        TusService,
        dataset_service=dataset_service,
    )

    permission_service = providers.Factory(
        PermissionService,
        permission_repository=permission_repository,
        user_service=user_service,
        audit=dataset_access_audit,
    )

    dataset_invitation_repository = providers.Factory(
        DatasetInvitationRepository,
        session_factory=db.provided.session,
    )

    dataset_anonymous_link_repository = providers.Factory(
        DatasetAnonymousLinkRepository,
        session_factory=db.provided.session,
    )

    access_history_service = providers.Factory(
        AccessHistoryService,
        dataset_service=dataset_service,
        event_repository=access_event_repository,
        user_repository=user_repository,
        invitation_repository=dataset_invitation_repository,
        anonymous_link_repository=dataset_anonymous_link_repository,
    )

    tenancy_invitation_repository = providers.Factory(
        TenancyInvitationRepository,
        session_factory=db.provided.session,
    )

    tenancy_invitation_service = providers.Factory(
        TenancyInvitationService,
        invitations=tenancy_invitation_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        tenancies=tenancy_repository,
        users=user_repository,
        user_service=user_service,
        notifier=tenancy_notifier,
    )

    tenancy_admin_service = providers.Factory(
        TenancyAdminService,
        tenancies=tenancy_repository,
        memberships=tenancy_membership_repository,
        membership_service=tenancy_membership_service,
        invitations=tenancy_invitation_repository,
        users=user_repository,
    )

    share_service = providers.Factory(
        ShareService,
        dataset_service=dataset_service,
        dataset_repository=dataset_repository,
        permission_repository=permission_repository,
        permission_service=permission_service,
        invitation_repository=dataset_invitation_repository,
        anonymous_link_repository=dataset_anonymous_link_repository,
        user_repository=user_repository,
        user_service=user_service,
        audit=dataset_access_audit,
        email_service=email_service,
        public_base_url=config.PUBLIC_BASE_URL,
        tenancy_repository=tenancy_repository,
        membership_service=tenancy_membership_service,
    )

    anonymous_link_service = providers.Factory(
        AnonymousLinkService,
        dataset_service=dataset_service,
        anonymous_link_repository=dataset_anonymous_link_repository,
        dataset_repository=dataset_repository,
        audit=dataset_access_audit,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    embargo_notification_repository = providers.Factory(
        EmbargoNotificationRepository,
        session_factory=db.provided.session,
    )

    embargo_notification_service = providers.Factory(
        EmbargoNotificationService,
        notification_repository=embargo_notification_repository,
        permission_repository=permission_repository,
        user_repository=user_repository,
        anonymous_link_repository=dataset_anonymous_link_repository,
        audit=dataset_access_audit,
        email_service=email_service,
        membership_service=tenancy_membership_service,
        public_base_url=config.PUBLIC_BASE_URL,
    )

    password_hasher = providers.Singleton(
        PasswordHasher,
        pepper=config.AUTH_PASSWORD_PEPPER,
    )

    auth_challenge_repository = providers.Factory(
        AuthChallengeRepository,
        session_factory=db.provided.session,
    )

    account_service = providers.Factory(
        AccountService,
        users=user_repository,
        user_service=user_service,
        challenges=auth_challenge_repository,
        emails=email_repository,
        email_service=email_service,
        hasher=password_hasher,
        challenge_pepper=config.AUTH_CHALLENGE_PEPPER,
        public_base_url=config.PUBLIC_BASE_URL,
    )
