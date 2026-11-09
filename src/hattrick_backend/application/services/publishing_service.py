from datetime import UTC

from sqlalchemy import func, select

from hattrick_backend.application.services.post_service import PostService
from hattrick_backend.core.exceptions import AppError
from hattrick_backend.domain.enums import Platform, PostState, PublicationStatus
from hattrick_backend.domain.lifecycle import require_publishable, validate_transition
from hattrick_backend.infrastructure.database.models import (
    ApprovalEvent,
    PlatformPublication,
    PublicationAttempt,
    utcnow,
)
from hattrick_backend.infrastructure.publishing.base import PublishPayload


def attempt_view(attempt):
    timestamp = attempt.completed_at or attempt.started_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return {
        "id": attempt.id,
        "platform": attempt.platform,
        "status": attempt.status,
        "revision": attempt.revision,
        "external_post_id": attempt.external_id,
        "timestamp": timestamp,
        "error": {"code": attempt.error_code, "message": attempt.error_message}
        if attempt.error_code
        else None,
    }


class PublishingService:
    def __init__(self, session, publishers):
        self.session = session
        self.publishers = publishers

    async def publish(self, post_id, request):
        post = await PostService(self.session).get(post_id, lock=True)
        require_publishable(post.state, post.approved_revision, post.revision)
        if not set(request.platforms).issubset(set(post.target_platforms)):
            raise AppError("invalid_platform", "Platform is not a target of this post", 422)
        if post.state == PostState.SCHEDULED:
            due = post.scheduled_at
            due = due.replace(tzinfo=UTC) if due.tzinfo is None else due.astimezone(UTC)
            if due > utcnow():
                raise AppError("not_due", "Scheduled publication is not due", 409)
        # Claim all platforms in one transaction before making any external call. Post row locking
        # serializes claims across instances. Crashes leave IN_PROGRESS for reconciliation.
        claimed = []
        results = []
        for platform in request.platforms:
            existing = await self.session.scalar(
                select(PublicationAttempt).where(
                    PublicationAttempt.post_id == post.id,
                    PublicationAttempt.platform == platform,
                    PublicationAttempt.idempotency_key == request.idempotency_key,
                )
            )
            if existing:
                results.append(attempt_view(existing))
                continue
            record = await self.session.scalar(
                select(PlatformPublication).where(
                    PlatformPublication.post_id == post.id, PlatformPublication.platform == platform
                )
            )
            if record and record.status in {
                PublicationStatus.IN_PROGRESS,
                PublicationStatus.UNKNOWN,
            }:
                raise AppError(
                    "publication_unresolved", "An earlier attempt requires reconciliation", 409
                )
            if record and record.status == PublicationStatus.SUCCEEDED:
                previous = await self.session.scalar(
                    select(PublicationAttempt).where(
                        PublicationAttempt.post_id == post.id,
                        PublicationAttempt.platform == platform,
                        PublicationAttempt.status == PublicationStatus.SUCCEEDED,
                    )
                )
                results.append(attempt_view(previous))
                continue
            if record is None:
                record = PlatformPublication(
                    post_id=post.id, platform=platform, status=PublicationStatus.IN_PROGRESS
                )
                self.session.add(record)
            record.status = PublicationStatus.IN_PROGRESS
            record.updated_at = utcnow()
            attempt = PublicationAttempt(
                post_id=post.id,
                platform=platform,
                revision=post.revision,
                idempotency_key=request.idempotency_key,
                status=PublicationStatus.IN_PROGRESS,
            )
            self.session.add(attempt)
            claimed.append((platform, attempt, record))
        content = post.content
        # Telegram MVP publishes plain text. Rendered cards are separately downloadable.
        text = "\n\n".join(
            [
                content["title"],
                content["explanation"],
                content["body"],
                content["key_takeaway"],
                content["caption"],
                " ".join(content["hashtags"]),
            ]
        )
        await self.session.commit()
        for platform, attempt, record in claimed:
            result = await self.publishers[Platform(platform)].publish(PublishPayload(text=text))
            # Reacquire the post lock to serialize aggregate state updates for parallel platforms.
            post = await PostService(self.session).get(post_id, lock=True)
            attempt.status = result.status
            attempt.external_id = result.external_id
            attempt.error_code = result.error_code
            attempt.error_message = result.error_message
            attempt.completed_at = result.timestamp
            record.status = result.status
            record.external_id = result.external_id
            record.updated_at = result.timestamp
            await self.session.flush()
            statuses = dict(
                (
                    await self.session.execute(
                        select(PlatformPublication.platform, PlatformPublication.status).where(
                            PlatformPublication.post_id == post.id
                        )
                    )
                ).all()
            )
            # Aggregate becomes PUBLISHED only when every target succeeds. Partial success keeps
            # approval and each platform's independent outcome. Failure never revokes approval.
            if all(statuses.get(p) == PublicationStatus.SUCCEEDED for p in post.target_platforms):
                if post.state != PostState.PUBLISHED:
                    validate_transition(post.state, PostState.PUBLISHED)
                    self.session.add(
                        ApprovalEvent(
                            post_id=post.id,
                            from_state=post.state,
                            to_state=PostState.PUBLISHED,
                            revision=post.revision,
                            actor="publishing-service",
                            note="All target platforms published",
                        )
                    )
                    post.state = PostState.PUBLISHED
                    post.updated_at = utcnow()
            await self.session.commit()
            results.append(attempt_view(attempt))
        return {"items": results}

    async def history(self, post_id, limit, offset):
        await PostService(self.session).get(post_id)
        total = await self.session.scalar(
            select(func.count())
            .select_from(PublicationAttempt)
            .where(PublicationAttempt.post_id == post_id)
        )
        attempts = (
            await self.session.scalars(
                select(PublicationAttempt)
                .where(PublicationAttempt.post_id == post_id)
                .order_by(PublicationAttempt.started_at.desc(), PublicationAttempt.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        records = (
            await self.session.scalars(
                select(PlatformPublication).where(PlatformPublication.post_id == post_id)
            )
        ).all()
        return {
            "items": [attempt_view(a) for a in attempts],
            "total": total,
            "limit": limit,
            "offset": offset,
            "platforms": [
                {
                    "platform": r.platform,
                    "status": r.status,
                    "external_post_id": r.external_id,
                    "timestamp": r.updated_at,
                }
                for r in records
            ],
        }
