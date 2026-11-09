from uuid import uuid4

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from hattrick_backend.application.services.post_service import PostService
from hattrick_backend.infrastructure.database.models import Asset
from hattrick_backend.schemas.posts import Content


def asset_view(asset):
    return {
        "id": asset.id,
        "post_id": asset.post_id,
        "revision": asset.revision,
        "media_type": asset.media_type,
        "width": asset.width,
        "height": asset.height,
        "theme": asset.theme,
        "created_at": asset.created_at,
        "download_url": f"/api/v1/posts/{asset.post_id}/assets/{asset.id}",
    }


class RenderingService:
    def __init__(self, session, renderer, storage):
        self.session = session
        self.renderer = renderer
        self.storage = storage

    async def render(self, post_id, theme):
        post = await PostService(self.session).get(post_id, lock=True)
        data = await run_in_threadpool(
            self.renderer.render, Content.model_validate(post.content), theme
        )
        asset_id = uuid4()
        key = f"{post.id}/{asset_id}.png"
        await run_in_threadpool(self.storage.put, key, data)
        asset = Asset(
            id=asset_id,
            post_id=post.id,
            revision=post.revision,
            storage_key=key,
            width=1080,
            height=1080,
            theme=theme.model_dump(),
        )
        self.session.add(asset)
        await self.session.commit()
        return asset_view(asset)

    async def list(self, post_id, limit=20, offset=0):
        await PostService(self.session).get(post_id)
        from sqlalchemy import func

        total = await self.session.scalar(
            select(func.count()).select_from(Asset).where(Asset.post_id == post_id)
        )
        assets = (
            await self.session.scalars(
                select(Asset)
                .where(Asset.post_id == post_id)
                .order_by(Asset.created_at.desc(), Asset.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return {
            "items": [asset_view(a) for a in assets],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
