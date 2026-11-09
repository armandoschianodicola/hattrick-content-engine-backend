import httpx
import pytest

from hattrick_backend.infrastructure.publishing.base import PublishPayload
from hattrick_backend.infrastructure.publishing.telegram import TelegramPublisher


@pytest.mark.parametrize(
    "status,data,expected",
    [
        (200, {"ok": True, "result": {"message_id": 123}}, "SUCCEEDED"),
        (403, {"ok": False, "description": "secret-token"}, "FAILED"),
        (429, {"ok": False, "parameters": {"retry_after": 10}}, "FAILED"),
        (503, {}, "UNKNOWN"),
        (200, {"ok": True}, "UNKNOWN"),
    ],
)
async def test_telegram_http_results(status, data, expected):
    def handle(request):
        assert request.url.path == "/botsecret-token/sendMessage"
        assert b'"chat_id":"chat"' in request.content
        return httpx.Response(status, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await TelegramPublisher("secret-token", "chat", client).publish(
            PublishPayload("Hi")
        )
    assert result.status == expected
    assert "secret-token" not in str(result)
    if expected == "SUCCEEDED":
        assert result.external_id == "123"


@pytest.mark.parametrize(
    "exception,expected",
    [
        (httpx.ReadTimeout, "UNKNOWN"),
        (httpx.ConnectError, "FAILED"),
    ],
)
async def test_network_outcomes(exception, expected):
    def handle(request):
        raise exception("secret-token", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await TelegramPublisher("secret-token", "chat", client).publish(
            PublishPayload("Hi")
        )
    assert result.status == expected and "secret-token" not in str(result)


async def test_unconfigured_and_oversized_messages_are_not_sent():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("must not send"))
    ) as client:
        result = await TelegramPublisher(None, None, client).publish(PublishPayload("Hi"))
        assert result.error_code == "not_configured"
        result = await TelegramPublisher("token", "chat", client).publish(
            PublishPayload("x" * 4097)
        )
        assert result.error_code == "message_too_long"
