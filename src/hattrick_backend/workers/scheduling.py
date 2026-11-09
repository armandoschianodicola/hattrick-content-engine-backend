"""A contract for future durable scheduling, not an API-process scheduler."""

from datetime import datetime
from typing import Protocol
from uuid import UUID


class ScheduledJobRunner(Protocol):
    async def execute_due_publications(self, now: datetime, batch_size: int = 20) -> list[UUID]:
        """Claim due posts transactionally; call the normal approval/idempotency guarded service."""
        ...
