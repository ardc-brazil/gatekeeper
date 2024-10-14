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
    CASBIN_MODEL_FILE: str = Field(..., description="Casbin model file")

    DOI_BASE_URL: str = Field(..., description="Base URL for DOI service")
    DOI_PREFIX: str = Field(..., description="Prefix/Repository for DOI service")
    DOI_LOGIN: str = Field(..., description="Login for DOI service")
    DOI_PASSWORD: str = Field(..., description="Password for DOI service")

    MINIO_URL: str = Field(..., description="Minio URL")
    MINIO_ACCESS_KEY: str = Field(..., description="Minio access key")
    MINIO_SECRET_KEY: str = Field(..., description="Minio secret key")
    MINIO_DATASET_BUCKET: str = Field(..., description="Minio dataset bucket")
    MINIO_DEFAULT_REGION_ID: str = Field(..., description="Minio default region id")
    MINIO_USE_SSL: bool = Field(..., description="Minio use SSL")

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
