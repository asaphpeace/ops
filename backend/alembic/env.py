import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from alembic import context

# Import all models so Alembic can autogenerate migrations
from app.database import Base  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.case import Case  # noqa: F401
from app.models.upgrade import Upgrade  # noqa: F401
from app.models.migration_project import MigrationProject  # noqa: F401
from app.models.release import Release  # noqa: F401
from app.models.training import TrainingGap, TrainingSession  # noqa: F401
from app.models.note import CustomerNote  # noqa: F401

config = context.config

# Override sqlalchemy.url from environment
database_url = os.environ.get("DATABASE_URL", "")
# Alembic needs the sync driver for migrations
sync_url = database_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
