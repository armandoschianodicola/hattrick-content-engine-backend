import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from hattrick_backend.core.config import Settings, get_settings
from hattrick_backend.domain.enums import Platform
from hattrick_backend.infrastructure.ai.fake import FakeAIProvider
from hattrick_backend.infrastructure.database.models import Base
from hattrick_backend.infrastructure.publishing.facebook import FacebookPublisher
from hattrick_backend.infrastructure.publishing.instagram import InstagramPublisher
from hattrick_backend.infrastructure.publishing.telegram import TelegramPublisher
from hattrick_backend.infrastructure.rendering.pillow_renderer import PillowRenderer
from hattrick_backend.infrastructure.retrieval.fake import FakeKnowledgeRetriever
from hattrick_backend.infrastructure.storage import LocalAssetStorage
from hattrick_backend.main import create_app


@pytest.fixture
async def sessions():
    # Unit/API suite is database-independent. PostgreSQL locking/vector tests are separate.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"backend": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def app(sessions, tmp_path):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        environment="test",
        api_key="test-admin-key",
        allow_illustrative_evidence=True,
    )
    app.state.sessions = sessions
    app.state.retriever = FakeKnowledgeRetriever()
    app.state.ai = FakeAIProvider()
    app.state.renderer = PillowRenderer()
    app.state.storage = LocalAssetStorage(tmp_path / "assets")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
        )
    ) as client:
        app.state.publishers = {
            Platform.TELEGRAM: TelegramPublisher("test-token", "test-chat", client),
            Platform.FACEBOOK: FacebookPublisher(),
            Platform.INSTAGRAM: InstagramPublisher(),
        }
        yield app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-admin-key"},
    ) as client:
        yield client
