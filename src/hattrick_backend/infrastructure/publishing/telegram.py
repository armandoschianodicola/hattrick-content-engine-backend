import httpx

from hattrick_backend.domain.enums import Platform, PublicationStatus
from hattrick_backend.infrastructure.publishing.base import PublishResult


class TelegramPublisher:
    def __init__(self, token: str | None, chat_id: str | None, client: httpx.AsyncClient):
        self.token = token
        self.chat_id = chat_id
        self.client = client

    def failure(self, code, message, ambiguous=False):
        return PublishResult(
            Platform.TELEGRAM,
            PublicationStatus.UNKNOWN if ambiguous else PublicationStatus.FAILED,
            error_code=code,
            error_message=message,
        )

    async def publish(self, payload):
        if not self.token or not self.chat_id:
            return self.failure(
                "not_configured", "Telegram credentials or destination not configured"
            )
        if len(payload.text.encode("utf-16-le")) // 2 > 4096:
            return self.failure(
                "message_too_long", "Telegram text exceeds the 4096 character limit"
            )
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": payload.text},
            )
            if response.status_code >= 500:
                return self.failure(
                    "provider_unavailable", "Telegram outcome requires reconciliation", True
                )
            data = response.json()
            if response.status_code >= 400 or data.get("ok") is not True:
                # Do not forward descriptions: upstream may echo credentials or destination data.
                return self.failure("provider_rejected", "Telegram rejected publication")
            external_id = data.get("result", {}).get("message_id")
            if not isinstance(external_id, int):
                return self.failure(
                    "invalid_response", "Telegram outcome requires reconciliation", True
                )
            return PublishResult(Platform.TELEGRAM, PublicationStatus.SUCCEEDED, str(external_id))
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return self.failure("connection_failed", "Could not connect to Telegram")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return self.failure("outcome_unknown", "Telegram outcome requires reconciliation", True)
