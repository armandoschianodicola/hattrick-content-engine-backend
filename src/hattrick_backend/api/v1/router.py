from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from hattrick_backend.api.dependencies import retrieval_dependency, session_dependency
from hattrick_backend.application.services.generation_service import GenerationService
from hattrick_backend.application.services.post_service import PostService
from hattrick_backend.application.services.publishing_service import PublishingService
from hattrick_backend.application.services.rendering_service import RenderingService
from hattrick_backend.core.config import get_settings
from hattrick_backend.core.exceptions import AppError
from hattrick_backend.core.security import require_admin
from hattrick_backend.domain.enums import PostState
from hattrick_backend.infrastructure.database.models import ApprovalEvent, Asset, PostRevision
from hattrick_backend.schemas.posts import (
    GenerationRequest,
    PostEdit,
    PostView,
    PublishRequest,
    RenderRequest,
    ReviewAction,
    ScheduleRequest,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_admin)])
Session = Annotated[object, Depends(session_dependency)]
Retrieval = Annotated[object, Depends(retrieval_dependency)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def page(items, total, limit, offset):
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/topics", tags=["topics"])
async def topics(retrieval: Retrieval, limit: Limit = 20, offset: Offset = 0):
    items, total = await retrieval.retriever.list_topics(limit, offset)
    return page(items, total, limit, offset)


@router.get("/topics/{topic_id}", tags=["topics"])
async def topic(topic_id: str, retrieval: Retrieval):
    return await retrieval.topic(topic_id)


@router.get("/topics/{topic_id}/documents", tags=["topics"])
async def documents(topic_id: str, retrieval: Retrieval, limit: Limit = 20, offset: Offset = 0):
    await retrieval.topic(topic_id)
    items, total = await retrieval.retriever.documents(topic_id, limit, offset)
    return page(items, total, limit, offset)


@router.get("/topics/{topic_id}/related", tags=["topics"])
async def related(topic_id: str, retrieval: Retrieval, limit: Limit = 20, offset: Offset = 0):
    await retrieval.topic(topic_id)
    items, total = await retrieval.retriever.related(topic_id, limit, offset)
    return page(items, total, limit, offset)


@router.get("/topics/{topic_id}/context", tags=["topics"])
async def context(
    topic_id: str,
    retrieval: Retrieval,
    query: str | None = Query(None, max_length=300),
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
):
    return {"items": await retrieval.context(topic_id, query, limit)}


@router.post("/generations", response_model=PostView, status_code=201, tags=["generation"])
async def generate(
    body: GenerationRequest,
    request: Request,
    session: Session,
    retrieval: Retrieval,
    settings=Depends(get_settings),
):
    return await GenerationService(
        retrieval, request.app.state.ai, session, settings.retrieval_limit
    ).generate(body)


@router.get("/posts", tags=["posts"])
async def posts(
    session: Session,
    limit: Limit = 20,
    offset: Offset = 0,
    state: PostState | None = None,
    topic_id: str | None = None,
):
    return await PostService(session).list(limit, offset, state, topic_id)


@router.get("/posts/{post_id}", response_model=PostView, tags=["posts"])
async def post(post_id: UUID, session: Session):
    service = PostService(session)
    return await service.view(await service.get(post_id))


@router.patch("/posts/{post_id}", response_model=PostView, tags=["posts"])
async def edit(post_id: UUID, body: PostEdit, session: Session, actor=Depends(require_admin)):
    return await PostService(session).edit(post_id, body, actor)


@router.post("/posts/{post_id}/submit-review", response_model=PostView, tags=["review"])
async def submit_review(
    post_id: UUID, body: ReviewAction, session: Session, actor=Depends(require_admin)
):
    return await PostService(session).transition(post_id, PostState.PENDING_REVIEW, body, actor)


@router.post("/posts/{post_id}/approve", response_model=PostView, tags=["review"])
async def approve(
    post_id: UUID, body: ReviewAction, session: Session, actor=Depends(require_admin)
):
    return await PostService(session).transition(post_id, PostState.APPROVED, body, actor)


@router.post("/posts/{post_id}/reject", response_model=PostView, tags=["review"])
async def reject(post_id: UUID, body: ReviewAction, session: Session, actor=Depends(require_admin)):
    return await PostService(session).transition(post_id, PostState.REJECTED, body, actor)


@router.post("/posts/{post_id}/reopen", response_model=PostView, tags=["review"])
async def reopen(post_id: UUID, body: ReviewAction, session: Session, actor=Depends(require_admin)):
    return await PostService(session).transition(post_id, PostState.DRAFT, body, actor)


@router.post("/posts/{post_id}/schedule", response_model=PostView, tags=["review"])
async def schedule(
    post_id: UUID, body: ScheduleRequest, session: Session, actor=Depends(require_admin)
):
    return await PostService(session).transition(
        post_id, PostState.SCHEDULED, body, actor, body.scheduled_at
    )


@router.get("/posts/{post_id}/history", tags=["posts"])
async def history(post_id: UUID, session: Session, limit: Limit = 20, offset: Offset = 0):
    await PostService(session).get(post_id)
    total = await session.scalar(
        select(func.count()).select_from(ApprovalEvent).where(ApprovalEvent.post_id == post_id)
    )
    events = (
        await session.scalars(
            select(ApprovalEvent)
            .where(ApprovalEvent.post_id == post_id)
            .order_by(ApprovalEvent.created_at, ApprovalEvent.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return page(
        [
            {
                "id": e.id,
                "from_state": e.from_state,
                "to_state": e.to_state,
                "revision": e.revision,
                "actor": e.actor,
                "note": e.note,
                "created_at": e.created_at,
            }
            for e in events
        ],
        total,
        limit,
        offset,
    )


@router.get("/posts/{post_id}/revisions", tags=["posts"])
async def revisions(post_id: UUID, session: Session, limit: Limit = 20, offset: Offset = 0):
    await PostService(session).get(post_id)
    total = await session.scalar(
        select(func.count()).select_from(PostRevision).where(PostRevision.post_id == post_id)
    )
    items = (
        await session.scalars(
            select(PostRevision)
            .where(PostRevision.post_id == post_id)
            .order_by(PostRevision.revision.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return page(
        [
            {
                "revision": r.revision,
                "content": r.content,
                "actor": r.actor,
                "created_at": r.created_at,
            }
            for r in items
        ],
        total,
        limit,
        offset,
    )


def rendering_service(request, session):
    return RenderingService(session, request.app.state.renderer, request.app.state.storage)


@router.post("/posts/{post_id}/render", status_code=201, tags=["rendering"])
async def render(post_id: UUID, body: RenderRequest, request: Request, session: Session):
    return await rendering_service(request, session).render(post_id, body)


@router.get("/posts/{post_id}/assets", tags=["rendering"])
async def assets(
    post_id: UUID, request: Request, session: Session, limit: Limit = 20, offset: Offset = 0
):
    return await rendering_service(request, session).list(post_id, limit, offset)


@router.get("/posts/{post_id}/assets/{asset_id}", tags=["rendering"])
async def download_asset(post_id: UUID, asset_id: UUID, request: Request, session: Session):
    asset = await session.scalar(
        select(Asset).where(Asset.id == asset_id, Asset.post_id == post_id)
    )
    if not asset:
        raise AppError("asset_not_found", "Asset not found", 404)
    data = await run_in_threadpool(request.app.state.storage.read, asset.storage_key)
    return Response(data, media_type=asset.media_type)


@router.post("/posts/{post_id}/publish", tags=["publishing"])
async def publish(post_id: UUID, body: PublishRequest, request: Request, session: Session):
    return await PublishingService(session, request.app.state.publishers).publish(post_id, body)


@router.get("/posts/{post_id}/publications", tags=["publishing"])
async def publications(
    post_id: UUID, request: Request, session: Session, limit: Limit = 20, offset: Offset = 0
):
    return await PublishingService(session, request.app.state.publishers).history(
        post_id, limit, offset
    )
