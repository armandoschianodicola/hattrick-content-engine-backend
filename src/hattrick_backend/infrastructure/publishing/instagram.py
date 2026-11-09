from hattrick_backend.domain.enums import Platform, PublicationStatus
from hattrick_backend.infrastructure.publishing.base import PublishResult


class InstagramPublisher:
    async def publish(self, payload):
        return PublishResult(
            Platform.INSTAGRAM,
            PublicationStatus.FAILED,
            error_code="not_implemented",
            error_message="Instagram publishing is not implemented",
        )
