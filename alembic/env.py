import asyncio

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from hattrick_backend.core.config import get_settings
from hattrick_backend.infrastructure.database.models import Base

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == "backend"
    return True


def configure(connection=None):
    options = dict(
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema="backend",
        compare_type=True,
    )
    if connection is not None:
        context.configure(connection=connection, **options)
    else:
        context.configure(
            url=get_settings().database_url.get_secret_value(),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )


def run_sync(connection):
    # Bootstrap only the backend namespace so Alembic can place its version table there.
    from sqlalchemy import text

    connection.execute(text("CREATE SCHEMA IF NOT EXISTS backend"))
    connection.commit()
    configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(
        get_settings().database_url.get_secret_value(), poolclass=pool.NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(run_sync)
    await engine.dispose()


if context.is_offline_mode():
    configure()
    context.execute("CREATE SCHEMA IF NOT EXISTS backend")
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
