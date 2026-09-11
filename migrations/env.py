from logging.config import fileConfig

from pydantic import PostgresDsn
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from app.config import settings


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# fileConfig disables every logger it does not name, which silences the whole
# application when alembic is invoked in-process at startup. Only configure
# logging when alembic owns the process, i.e. the CLI.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.database import Base  # noqa: E402
from app.model.db import casbin_rule  # noqa: E402, F401
from app.model.db import client  # noqa: E402, F401
from app.model.db import dataset  # noqa: E402, F401
from app.model.db import tenancy  # noqa: E402, F401
from app.model.db import user  # noqa: E402, F401
from app.model.db import doi  # noqa: E402, F401

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url() -> PostgresDsn:
    return settings.DATABASE_URL


# Owned by casbin_sqlalchemy_adapter, not by our models, so it is absent from
# Base.metadata and autogenerate would propose dropping it on every revision.
EXTERNALLY_MANAGED_TABLES = {"casbin_rule"}


def include_object(object, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name in EXTERNALLY_MANAGED_TABLES:
        return False

    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url.unicode_string(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url().unicode_string()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
