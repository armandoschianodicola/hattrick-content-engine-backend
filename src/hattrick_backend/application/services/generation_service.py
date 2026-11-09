from pydantic import ValidationError

from hattrick_backend.application.prompts.educational_post import PROMPT_VERSION, build_prompt
from hattrick_backend.application.services.post_service import PostService
from hattrick_backend.core.exceptions import AppError, InsufficientEvidence
from hattrick_backend.infrastructure.ai.openai_provider import GenerationResponse
from hattrick_backend.infrastructure.database.models import (
    Generation,
    Post,
    PostRevision,
    PostSource,
)
from hattrick_backend.schemas.knowledge import SourceReference


class GenerationService:
    def __init__(self, retrieval, ai, session, retrieval_limit=8):
        self.retrieval = retrieval
        self.ai = ai
        self.session = session
        self.retrieval_limit = retrieval_limit

    async def generate(self, options):
        chunks = await self.retrieval.context(options.topic_id, options.query, self.retrieval_limit)
        related, _ = await self.retrieval.retriever.related(options.topic_id, 100, 0)
        result = await self.ai.generate(build_prompt(options, chunks, related))
        try:
            response = GenerationResponse.model_validate(result.response)
        except ValidationError:
            raise AppError(
                "invalid_generation", "AI returned invalid structured content", 502
            ) from None
        if not response.sufficient_evidence or response.content is None:
            raise InsufficientEvidence()
        content = response.content
        if not set(content.source_chunk_ids).issubset({c.id for c in chunks}):
            raise AppError("invalid_citation", "AI cited unknown evidence", 502)
        if not set(content.related_topic_ids).issubset({t.id for t in related}):
            raise AppError("invalid_related_topic", "AI cited unknown related topics", 502)
        if any(c.document.authority == "illustrative" for c in chunks):
            # Deterministic disclosure remains visible even if the model omits its instruction.
            content.explanation = (
                "Illustrative, not verified game mechanics. " + content.explanation[:550]
            )
        post = Post(
            topic_id=options.topic_id,
            content=content.model_dump(mode="json"),
            target_platforms=[p.value for p in options.target_platforms],
            state="DRAFT",
        )
        self.session.add(post)
        await self.session.flush()
        self.session.add(
            Generation(
                post_id=post.id,
                model=result.model,
                prompt_version=PROMPT_VERSION,
                options=options.model_dump(mode="json"),
                usage=result.usage,
            )
        )
        self.session.add(
            PostRevision(
                post_id=post.id, revision=1, content=post.content, actor="generation-service"
            )
        )
        # Persist provenance for every supplied chunk, without copying source document text.
        for chunk in chunks:
            ref = SourceReference(
                chunk_id=chunk.id,
                document_id=chunk.document.id,
                source_id=chunk.document.source_id,
                title=chunk.document.title,
                source_url=chunk.document.source_url,
                authority=chunk.document.authority,
                checksum=chunk.checksum,
                score=chunk.score,
            )
            self.session.add(
                PostSource(
                    post_id=post.id, chunk_id=chunk.id, provenance=ref.model_dump(mode="json")
                )
            )
        await self.session.commit()
        return await PostService(self.session).view(post)
