from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from hattrick_backend.application.prompts.educational_post import SYSTEM_PROMPT, build_prompt
from hattrick_backend.application.services.generation_service import GenerationService
from hattrick_backend.application.services.retrieval_service import RetrievalService
from hattrick_backend.core.exceptions import AppError, InsufficientEvidence
from hattrick_backend.infrastructure.ai.fake import FakeAIProvider
from hattrick_backend.infrastructure.ai.openai_provider import AIResult, GenerationResponse
from hattrick_backend.infrastructure.database.models import Post, PostSource
from hattrick_backend.infrastructure.retrieval.fake import FakeKnowledgeRetriever
from hattrick_backend.schemas.posts import Content, GenerationRequest


async def test_fixture_topics_documents_relationships():
    retriever = FakeKnowledgeRetriever()
    topics, count = await retriever.list_topics(1, 0)
    assert count == 5 and topics[0].id == "weather"
    docs, count = await retriever.documents("weather", 20, 0)
    assert count == 2 and all(d.authority == "illustrative" for d in docs)
    related, _ = await retriever.related("weather", 20, 0)
    assert {"specialties", "attendance"} <= {t.id for t in related}
    context = await RetrievalService(retriever, True).context("weather", None)
    assert len(context) == 2 and all(c.checksum for c in context)


async def test_evidence_gates_and_missing_topic():
    retriever = FakeKnowledgeRetriever()
    with pytest.raises(InsufficientEvidence):
        await RetrievalService(retriever).context("weather", None)
    with pytest.raises(AppError, match="Topic not found"):
        await RetrievalService(retriever).topic("missing")
    with pytest.raises(InsufficientEvidence):
        await RetrievalService(retriever, True).context("tactics", None)


async def test_authority_ranking_filtering_deduplication():
    retriever = FakeKnowledgeRetriever()
    official = retriever.chunks[0].model_copy(deep=True)
    official.id = "official"
    official.document.authority = "official"
    official.score = 0.3
    wrong_topic = official.model_copy(deep=True)
    wrong_topic.id = "wrong"
    wrong_topic.topic_ids = ["attendance"]
    retriever.search = AsyncMock(
        return_value=[retriever.chunks[0], official, official, wrong_topic]
    )
    chunks = await RetrievalService(retriever, True).context("weather", "weather")
    assert [c.id for c in chunks] == ["official", "sample-weather-0"]


async def test_generation_persists_draft_and_provenance(sessions):
    async with sessions() as session:
        service = GenerationService(
            RetrievalService(FakeKnowledgeRetriever(), True), FakeAIProvider(), session
        )
        post = await service.generate(GenerationRequest(topic_id="weather"))
        assert post.state == "DRAFT" and post.approved_revision is None
        assert post.generation["prompt_version"] == "educational-v1"
        assert len(post.source_references) == 2
        refs = (await session.scalars(select(PostSource))).all()
        assert all("text" not in r.provenance for r in refs)


async def test_insufficient_context_never_calls_ai_or_persists(sessions):
    ai = AsyncMock()
    async with sessions() as session:
        with pytest.raises(InsufficientEvidence):
            await GenerationService(
                RetrievalService(FakeKnowledgeRetriever()), ai, session
            ).generate(GenerationRequest(topic_id="weather"))
        ai.generate.assert_not_called()
        assert await session.scalar(select(func.count()).select_from(Post)) == 0


async def test_refusal_and_fabricated_citations_are_not_persisted(sessions):
    retrieval = RetrievalService(FakeKnowledgeRetriever(), True)
    options = GenerationRequest(topic_id="weather")
    chunks = await retrieval.context("weather", None)
    result = await FakeAIProvider().generate(build_prompt(options, chunks, []))
    result.response.content.source_chunk_ids = ["invented-source"]
    ai = AsyncMock()
    async with sessions() as session:
        ai.generate.return_value = result
        with pytest.raises(AppError, match="unknown evidence"):
            await GenerationService(retrieval, ai, session).generate(options)
        ai.generate.return_value = AIResult(
            GenerationResponse(sufficient_evidence=False, content=None), "fake", {}
        )
        with pytest.raises(InsufficientEvidence):
            await GenerationService(retrieval, ai, session).generate(options)
        assert await session.scalar(select(func.count()).select_from(Post)) == 0


def test_structured_content_validation_and_prompt_boundary():
    with pytest.raises(ValidationError):
        Content.model_validate({"title": ""})
    assert "untrusted DATA" in SYSTEM_PROMPT
    assert "Do not invent mechanics" in SYSTEM_PROMPT


async def test_invalid_provider_response_is_revalidated_before_persistence(sessions):
    retriever = FakeKnowledgeRetriever()
    result = await FakeAIProvider().generate(
        build_prompt(GenerationRequest(topic_id="weather"), retriever.chunks, [])
    )
    result.response.content.body = "x" * 4001
    ai = AsyncMock()
    ai.generate.return_value = result
    async with sessions() as session:
        with pytest.raises(AppError) as exc:
            await GenerationService(RetrievalService(retriever, True), ai, session).generate(
                GenerationRequest(topic_id="weather")
            )
        assert exc.value.code == "invalid_generation"
        assert await session.scalar(select(func.count()).select_from(Post)) == 0
