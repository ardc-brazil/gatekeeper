import logging
import os
from typing import Any, Optional
from pydantic import ConfigDict, Field, ValidationInfo, field_validator, PostgresDsn
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    model_config = ConfigDict(extra='ignore')
    
    APP_TITLE: str = Field(default='gatekeeper')
    DEBUG: bool = False
    LOG_LEVEL: str = Field(..., description="Log level of the application")
    ENVIRONMENT: str = Field(..., description="Environment of the application")

    POSTGRES_HOST: str = Field(..., description="Postgres database host")
    POSTGRES_PORT: str = Field(..., description="Postgres database port")
    POSTGRES_USER: str = Field(..., description="Postgres database user")
    POSTGRES_PASSWORD: str = Field(..., description="Postgres database password")
    POSTGRES_DB: str = Field(..., description="Postgres database name")
    DATABASE_URL: Optional[PostgresDsn] = Field(default=None, description="Database URL")

    AUTH_USER_TOKEN_SECRET: str = Field(..., description="Secret key for user token")
    CASBIN_MODEL_FILE: str = Field(..., description="Casbin model file")

    @field_validator('DATABASE_URL', mode='before')
    def build_database_url(cls, value: Optional[str], values: ValidationInfo) -> str:
        if isinstance(value, str):
            return value
        return PostgresDsn.build(
            scheme='postgresql+psycopg2',
            username=values.data.get('POSTGRES_USER'),
            password=values.data.get('POSTGRES_PASSWORD'),
            host=values.data.get('POSTGRES_HOST'),
            port=int(values.data.get('POSTGRES_PORT')),
            path=values.data.get("POSTGRES_DB"),
        )

env_name = os.getenv("ENV", "local")
config_file = f"{env_name}.env"
logger = logging.getLogger("uvicorn")
logger.info(f"Using config file: {config_file}")
settings = Config(_env_file=config_file, _env_file_encoding='utf-8')
