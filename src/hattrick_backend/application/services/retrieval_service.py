from typing import Protocol

from hattrick_backend.core.exceptions import AppError, InsufficientEvidence
from hattrick_backend.schemas.knowledge import Chunk, Document, Topic


class KnowledgeRetriever(Protocol):
    async def list_topics(self, limit: int, offset: int) -> tuple[list[Topic], int]: ...
    async def get_topic(self, topic_id: str) -> Topic | None: ...
    async def documents(
        self, topic_id: str, limit: int, offset: int
    ) -> tuple[list[Document], int]: ...
    async def related(self, topic_id: str, limit: int, offset: int) -> tuple[list[Topic], int]: ...
    async def search(self, query: str, topic_id: str | None, limit: int) -> list[Chunk]: ...


class RetrievalService:
    def __init__(self, retriever: KnowledgeRetriever, allow_illustrative: bool = False):
        self.retriever = retriever
        self.allow_illustrative = allow_illustrative

    async def topic(self, topic_id: str) -> Topic:
        topic = await self.retriever.get_topic(topic_id)
        if not topic:
            raise AppError("topic_not_found", "Topic not found", 404)
        return topic

    async def context(self, topic_id: str, query: str | None, limit: int = 8) -> list[Chunk]:
        topic = await self.topic(topic_id)
        chunks = await self.retriever.search(query or topic.name, topic_id, limit)
        # Authority is distinct from similarity. Unknown/illustrative evidence must not silently
        # become verified mechanics. Include related context only if it is tagged for this topic.
        ranks = {"official": 0, "community": 1, "personal": 2, "illustrative": 3}
        unique = {}
        for chunk in chunks:
            if topic_id not in chunk.topic_ids or not chunk.text.strip():
                continue
            if chunk.document.authority == "illustrative" and not self.allow_illustrative:
                continue
            unique.setdefault(chunk.id, chunk)
        selected = sorted(unique.values(), key=lambda c: (ranks[c.document.authority], -c.score))
        if not selected:
            raise InsufficientEvidence()
        return selected[:limit]
