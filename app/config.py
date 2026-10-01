import logging
import os
from typing import Optional
from pydantic import ConfigDict, Field, ValidationInfo, field_validator, PostgresDsn
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    model_config = ConfigDict(extra="ignore")

    APP_TITLE: str = Field(default="gatekeeper")
    DEBUG: bool = False
    LOG_LEVEL: str = Field(..., description="Log level of the application")
    CASBIN_LOG_LEVEL: str = Field(
        logging.INFO, description="Log level of the casbin enforcer"
    )
    SQLALCHEMY_LOG_LEVEL: str = Field(
        logging.WARN, description="Log level of the SQLAlchemy"
    )
    ENVIRONMENT: str = Field(..., description="Environment of the application")

    POSTGRES_HOST: str = Field(..., description="Postgres database host")
    POSTGRES_PORT: str = Field(..., description="Postgres database port")
    POSTGRES_USER: str = Field(..., description="Postgres database user")
    POSTGRES_PASSWORD: str = Field(..., description="Postgres database password")
    POSTGRES_DB: str = Field(..., description="Postgres database name")
    DATABASE_URL: Optional[PostgresDsn] = Field(
        default=None, description="Database URL"
    )
    DATABASE_LOG_ENABLED: bool = Field(
        default=False, description="Enable database logging"
    )

    AUTH_FILE_UPLOAD_TOKEN_SECRET: str = Field(
        ..., description="Secret key for file upload token"
    )
    AUTH_CLIENT_SECRET_PEPPER: str = Field(
        ...,
        min_length=16,
        description="Server-side key the stored client secret hashes are derived from",
    )
    CASBIN_MODEL_FILE: str = Field(..., description="Casbin model file")

    DOI_BASE_URL: str = Field(..., description="Base URL for DOI service")
    DOI_PREFIX: str = Field(..., description="Prefix/Repository for DOI service")
    DOI_LOGIN: str = Field(..., description="Login for DOI service")
    DOI_PASSWORD: str = Field(..., description="Password for DOI service")
    DOI_TIMEOUT_SECONDS: float = Field(
        15, description="Connect and read timeout for DOI service calls"
    )

    MINIO_URL: str = Field(..., description="Minio URL")
    MINIO_ACCESS_KEY: str = Field(..., description="Minio access key")
    MINIO_SECRET_KEY: str = Field(..., description="Minio secret key")
    MINIO_DATASET_BUCKET: str = Field(..., description="Minio dataset bucket")
    MINIO_DEFAULT_REGION_ID: str = Field(..., description="Minio default region id")
    MINIO_USE_SSL: bool = Field(..., description="Minio use SSL")
    MINIO_TIMEOUT_SECONDS: int = Field(
        10, description="Read timeout for object storage calls"
    )
    MINIO_CONNECT_TIMEOUT_SECONDS: float = Field(
        2, description="Connect timeout for object storage calls"
    )
    MINIO_RETRIES: int = Field(2, description="Retries for object storage calls")

    METRICS_PORT: int = Field(
        9095, description="Port the Prometheus metrics are served on"
    )

    EMAIL_ENABLED: bool = Field(
        False, description="Send queued email; when false it stays pending"
    )
    EMAIL_FROM_NAME: str = Field("DataMap", description="Sender display name")
    EMAIL_FROM_ADDRESS: str = Field(
        "no-reply@datamap.pcs.usp.br", description="Sender address"
    )
    EMAIL_REPLY_TO: Optional[str] = Field(None, description="Reply-To address")
    SMTP_HOST: str = Field("localhost", description="SMTP server host")
    SMTP_PORT: int = Field(587, description="SMTP server port")
    SMTP_USERNAME: Optional[str] = Field(None, description="SMTP user")
    SMTP_PASSWORD: Optional[str] = Field(None, description="SMTP password")
    SMTP_STARTTLS: bool = Field(
        True, description="Upgrade the connection with STARTTLS"
    )
    SMTP_TIMEOUT_SECONDS: float = Field(30, description="SMTP socket timeout")
    PUBLIC_BASE_URL: str = Field(
        "https://datamap.pcs.usp.br", description="Origin of links in messages"
    )
    BUILD_COMMIT: str = Field("unknown", description="Commit the image was built from")

    @field_validator("DATABASE_URL", mode="before")
    def build_database_url(cls, value: Optional[str], values: ValidationInfo) -> str:
        if isinstance(value, str):
            return value
        return PostgresDsn.build(
            scheme="postgresql+psycopg2",
            username=values.data.get("POSTGRES_USER"),
            password=values.data.get("POSTGRES_PASSWORD"),
            host=values.data.get("POSTGRES_HOST"),
            port=int(values.data.get("POSTGRES_PORT")),
            path=values.data.get("POSTGRES_DB"),
        )


env_name = os.getenv("ENVIRONMENT", "local")
config_file = f"{env_name}.env"
logger = logging.getLogger("uvicorn")
logger.info(f"Using config file: {config_file}")
settings = Config(_env_file=config_file, _env_file_encoding="utf-8")
