from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from hattrick_backend.domain.enums import Platform, PublicationStatus
from hattrick_backend.infrastructure.database.models import utcnow


@dataclass
class PublishPayload:
    text: str


@dataclass
class PublishResult:
    platform: Platform
    status: PublicationStatus
    external_id: str | None = None
    timestamp: datetime = field(default_factory=utcnow)
    error_code: str | None = None
    error_message: str | None = None


class Publisher(Protocol):
    async def publish(self, payload: PublishPayload) -> PublishResult: ...
