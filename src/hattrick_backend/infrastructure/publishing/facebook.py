from hattrick_backend.domain.enums import Platform, PublicationStatus
from hattrick_backend.infrastructure.publishing.base import PublishResult


class FacebookPublisher:
    async def publish(self, payload):
        return PublishResult(
            Platform.FACEBOOK,
            PublicationStatus.FAILED,
            error_code="not_implemented",
            error_message="Facebook publishing is not implemented",
        )
