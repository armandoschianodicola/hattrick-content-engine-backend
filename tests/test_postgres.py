"""Opt-in integration checks against a dedicated PostgreSQL test database."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hattrick_backend.application.services.generation_service import GenerationService
from hattrick_backend.application.services.post_service import PostService
from hattrick_backend.application.services.publishing_service import PublishingService
from hattrick_backend.application.services.retrieval_service import RetrievalService
from hattrick_backend.core.exceptions import AppError
from hattrick_backend.domain.enums import Platform, PostState, PublicationStatus
from hattrick_backend.infrastructure.ai.fake import FakeAIProvider
from hattrick_backend.infrastructure.database.models import PublicationAttempt
from hattrick_backend.infrastructure.publishing.base import PublishResult
from hattrick_backend.infrastructure.retrieval.fake import FakeKnowledgeRetriever
from hattrick_backend.infrastructure.retrieval.pgvector_retriever import PgvectorRetriever
from hattrick_backend.schemas.posts import GenerationRequest, PublishRequest, ReviewAction

TEST_URL = os.getenv("TEST_DATABASE_URL")
CONTRACT_SQL = Path("tests/fixtures/knowledge_v1.sql").read_text(encoding="utf-8")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="Set TEST_DATABASE_URL for PostgreSQL tests")


@pytest.fixture
async def pg_sessions():
    # Test-only fixture DDL must never run against an ingestion or production database.
    if not make_url(TEST_URL).database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a dedicated database ending in _test")
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as connection:
        raw = await connection.get_raw_connection()
        await raw.driver_connection.execute(CONTRACT_SQL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_pgvector_adapter_contract(pg_sessions):
    embedder = AsyncMock()
    embedder.embed.return_value = [1.0] + [0.0] * 1535
    retriever = PgvectorRetriever(pg_sessions, embedder, "text-embedding-3-small", 1536, 0.25)
    topics, total = await retriever.list_topics(1, 0)
    assert len(topics) == 1 and total == 2
    assert (await retriever.get_topic("weather")).name == "Weather"
    documents, total = await retriever.documents("weather", 20, 0)
    assert total == 1 and documents[0].metadata == {"verified": False}
    related, _ = await retriever.related("attendance", 20, 0)
    assert related[0].id == "weather"
    chunks = await retriever.search("weather", "weather", 8)
    assert len(chunks) == 1 and chunks[0].score == pytest.approx(1)
    assert chunks[0].document.source_id == "test-source"
    assert len(await retriever.search("all", None, 8)) == 1
    assert await retriever.search("missing", "missing", 8) == []
    embedder.embed.return_value = [0.0] * 10
    with pytest.raises(AppError, match="Embedding violates"):
        await retriever.search("weather", "weather", 8)


async def test_concurrent_publication_claims_prevent_duplicates(pg_sessions):
    async with pg_sessions() as session:
        post = await GenerationService(
            RetrievalService(FakeKnowledgeRetriever(), True), FakeAIProvider(), session
        ).generate(GenerationRequest(topic_id="weather"))
        service = PostService(session)
        for target in (PostState.PENDING_REVIEW, PostState.APPROVED):
            await service.transition(post.id, target, ReviewAction(expected_revision=1), "test")

    async def send(payload):
        # Yield to the competing request after claim commit, without a timing-based sleep.
        await asyncio.sleep(0)
        return PublishResult(Platform.TELEGRAM, PublicationStatus.SUCCEEDED, "123")

    publisher = AsyncMock()
    publisher.publish.side_effect = send

    async def publish():
        async with pg_sessions() as session:
            return await PublishingService(session, {Platform.TELEGRAM: publisher}).publish(
                post.id,
                PublishRequest(platforms=[Platform.TELEGRAM], idempotency_key="concurrent-001"),
            )

    results = await asyncio.gather(publish(), publish())
    assert len(results) == 2 and publisher.publish.await_count == 1
    async with pg_sessions() as session:
        attempts = (
            await session.scalars(
                select(PublicationAttempt).where(PublicationAttempt.post_id == post.id)
            )
        ).all()
        assert len(attempts) == 1 and attempts[0].status == "SUCCEEDED"
