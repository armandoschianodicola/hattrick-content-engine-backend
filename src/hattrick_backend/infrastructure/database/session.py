from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hattrick_backend.core.config import Settings


def create_session_factory(settings: Settings):
    engine = create_async_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
