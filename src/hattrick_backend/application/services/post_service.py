from datetime import UTC, datetime

from sqlalchemy import func, select

from hattrick_backend.core.exceptions import AppError
from hattrick_backend.domain.enums import PostState
from hattrick_backend.domain.lifecycle import validate_transition
from hattrick_backend.infrastructure.database.models import (
    ApprovalEvent,
    Generation,
    Post,
    PostRevision,
    PostSource,
    utcnow,
)
from hattrick_backend.schemas.posts import Content, PostView


class PostService:
    def __init__(self, session):
        self.session = session

    async def get(self, post_id, lock=False):
        query = select(Post).where(Post.id == post_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        post = await self.session.scalar(query)
        if not post:
            raise AppError("post_not_found", "Post not found", 404)
        return post

    async def view(self, post):
        generation = await self.session.scalar(
            select(Generation).where(Generation.post_id == post.id)
        )
        sources = (
            await self.session.scalars(
                select(PostSource)
                .where(PostSource.post_id == post.id)
                .order_by(PostSource.chunk_id)
            )
        ).all()
        return PostView(
            id=post.id,
            topic_id=post.topic_id,
            state=post.state,
            revision=post.revision,
            approved_revision=post.approved_revision,
            content=Content.model_validate(post.content),
            target_platforms=post.target_platforms,
            source_references=[s.provenance for s in sources],
            generation={
                "model": generation.model,
                "prompt_version": generation.prompt_version,
                "options": generation.options,
                "usage": generation.usage,
            }
            if generation
            else {},
            created_at=post.created_at,
            updated_at=post.updated_at,
            scheduled_at=post.scheduled_at,
        )

    async def list(self, limit, offset, state=None, topic_id=None):
        criteria = []
        if state:
            criteria.append(Post.state == state)
        if topic_id:
            criteria.append(Post.topic_id == topic_id)
        total = await self.session.scalar(select(func.count()).select_from(Post).where(*criteria))
        posts = (
            await self.session.scalars(
                select(Post)
                .where(*criteria)
                .order_by(Post.created_at.desc(), Post.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return {
            "items": [await self.view(p) for p in posts],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def check_revision(post, expected):
        if post.revision != expected:
            raise AppError(
                "revision_conflict", "Post revision has changed; reload before editing", 409
            )

    async def edit(self, post_id, edit, actor):
        post = await self.get(post_id, lock=True)
        self.check_revision(post, edit.expected_revision)
        if post.state != PostState.DRAFT:
            raise AppError(
                "edit_not_allowed", "Only drafts may be edited; reopen rejected posts first", 409
            )
        source_ids = set(
            (
                await self.session.scalars(
                    select(PostSource.chunk_id).where(PostSource.post_id == post.id)
                )
            ).all()
        )
        if not set(edit.content.source_chunk_ids).issubset(source_ids):
            raise AppError(
                "invalid_citation", "Edits must retain references from generation context", 422
            )
        post.content = edit.content.model_dump(mode="json")
        post.revision += 1
        post.approved_revision = None
        post.updated_at = utcnow()
        self.session.add(
            PostRevision(post_id=post.id, revision=post.revision, content=post.content, actor=actor)
        )
        await self.session.commit()
        return await self.view(post)

    async def transition(self, post_id, target, action, actor, scheduled_at=None):
        post = await self.get(post_id, lock=True)
        self.check_revision(post, action.expected_revision)
        validate_transition(post.state, target)
        if target == PostState.SCHEDULED:
            if not scheduled_at or scheduled_at.tzinfo is None or scheduled_at <= datetime.now(UTC):
                raise AppError(
                    "invalid_schedule", "Schedule requires a future timezone-aware timestamp", 422
                )
            post.scheduled_at = scheduled_at
        else:
            post.scheduled_at = None
        if target == PostState.APPROVED:
            post.approved_revision = post.revision
        if target in {PostState.DRAFT, PostState.REJECTED}:
            post.approved_revision = None
        self.session.add(
            ApprovalEvent(
                post_id=post.id,
                from_state=post.state,
                to_state=target,
                revision=post.revision,
                actor=actor,
                note=action.note,
            )
        )
        post.state = target
        post.updated_at = utcnow()
        await self.session.commit()
        return await self.view(post)
