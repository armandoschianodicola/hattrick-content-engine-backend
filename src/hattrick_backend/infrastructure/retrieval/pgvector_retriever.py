import math

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from hattrick_backend.core.exceptions import AppError
from hattrick_backend.schemas.knowledge import Chunk, Document, Topic


class PgvectorRetriever:
    """Read-only adapter for docs/knowledge-contract.md; owns no knowledge migrations."""

    def __init__(self, sessions, embedder, model: str, dimensions: int, min_similarity: float):
        self.sessions = sessions
        self.embedder = embedder
        self.model = model
        self.dimensions = dimensions
        self.min_similarity = min_similarity

    async def _rows(self, sql, params=None):
        try:
            async with self.sessions() as session:
                result = await session.execute(text(sql), params or {})
                return result.mappings().all()
        except SQLAlchemyError:
            raise AppError(
                "knowledge_unavailable",
                "Knowledge contract unavailable; integrate ingestion schema v1",
                503,
            ) from None

    async def _page(self, sql, params, limit, offset):
        total = (await self._rows(f"SELECT count(*) AS total FROM ({sql}) AS items", params))[0][
            "total"
        ]
        rows = await self._rows(
            sql + " LIMIT :limit OFFSET :offset", {**params, "limit": limit, "offset": offset}
        )
        return rows, total

    async def list_topics(self, limit, offset):
        rows, total = await self._page(
            "SELECT id, name, description FROM knowledge.topics ORDER BY id", {}, limit, offset
        )
        return [Topic.model_validate(r) for r in rows], total

    async def get_topic(self, topic_id):
        rows = await self._rows(
            "SELECT id, name, description FROM knowledge.topics WHERE id=:id", {"id": topic_id}
        )
        return Topic.model_validate(rows[0]) if rows else None

    async def documents(self, topic_id, limit, offset):
        rows, total = await self._page(
            """
            SELECT DISTINCT d.id, d.title, d.source_id, s.url AS source_url, s.authority, d.metadata
            FROM knowledge.documents d JOIN knowledge.sources s ON s.id=d.source_id
            JOIN knowledge.chunks c ON c.document_id=d.id
            JOIN knowledge.chunk_topics ct ON ct.chunk_id=c.id
            WHERE ct.topic_id=:id ORDER BY d.id
        """,
            {"id": topic_id},
            limit,
            offset,
        )
        return [Document.model_validate(r) for r in rows], total

    async def related(self, topic_id, limit, offset):
        rows, total = await self._page(
            """
            SELECT DISTINCT t.id, t.name, t.description FROM knowledge.topics t
            JOIN knowledge.topic_relationships r ON
                (r.related_topic_id=t.id AND r.topic_id=:id)
                OR (r.topic_id=t.id AND r.related_topic_id=:id)
            WHERE t.id != :id ORDER BY t.id
        """,
            {"id": topic_id},
            limit,
            offset,
        )
        return [Topic.model_validate(r) for r in rows], total

    async def search(self, query, topic_id, limit):
        embedding = await self.embedder.embed(query)
        if len(embedding) != self.dimensions or not all(math.isfinite(v) for v in embedding):
            raise AppError("embedding_mismatch", "Embedding violates knowledge contract", 503)
        vector = "[" + ",".join(str(float(v)) for v in embedding) + "]"
        rows = await self._rows(
            """
            SELECT c.id, c.text, c.checksum, d.id AS document_id, d.title, d.source_id,
                   s.url AS source_url, s.authority, d.metadata,
                   ARRAY(SELECT ct.topic_id FROM knowledge.chunk_topics ct WHERE ct.chunk_id=c.id)
                     AS topic_ids,
                   1-(c.embedding <=> CAST(:vector AS vector)) AS score
            FROM knowledge.chunks c JOIN knowledge.documents d ON d.id=c.document_id
            JOIN knowledge.sources s ON s.id=d.source_id
            WHERE c.embedding_model=:model AND c.embedding_dimensions=:dimensions
              AND (CAST(:topic AS text) IS NULL OR EXISTS (SELECT 1 FROM knowledge.chunk_topics ct
                   WHERE ct.chunk_id=c.id AND ct.topic_id=:topic))
              AND 1-(c.embedding <=> CAST(:vector AS vector)) >= :minimum
            ORDER BY c.embedding <=> CAST(:vector AS vector), c.id LIMIT :limit
        """,
            {
                "vector": vector,
                "model": self.model,
                "dimensions": self.dimensions,
                "topic": topic_id,
                "minimum": self.min_similarity,
                "limit": limit,
            },
        )
        return [
            Chunk(
                id=r["id"],
                text=r["text"],
                checksum=r["checksum"],
                score=r["score"],
                topic_ids=r["topic_ids"],
                document=Document(
                    id=r["document_id"],
                    title=r["title"],
                    source_id=r["source_id"],
                    source_url=r["source_url"],
                    authority=r["authority"],
                    metadata=r["metadata"],
                ),
            )
            for r in rows
        ]
