from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError

from hattrick_backend.core.config import Settings
from hattrick_backend.core.exceptions import AppError, InsufficientEvidence
from hattrick_backend.infrastructure.ai.openai_provider import (
    GenerationResponse,
    OpenAIProvider,
)


async def test_structured_output_parameters_and_optional_temperature():
    client = AsyncMock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=GenerationResponse(sufficient_evidence=False, content=None),
        model="configured-model",
        usage=None,
    )
    settings = Settings(_env_file=None, openai_model="configured-model")
    provider = OpenAIProvider(settings, client)
    result = await provider.generate("test evidence")
    assert not result.response.sufficient_evidence
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "configured-model"
    assert kwargs["text_format"] is GenerationResponse and kwargs["store"] is False
    assert "temperature" not in kwargs
    settings.openai_temperature = 0.2
    await provider.generate("test evidence")
    assert client.responses.parse.call_args.kwargs["temperature"] == 0.2
    await provider.close()
    client.close.assert_awaited_once()


async def test_refusal_upstream_failure_and_missing_credentials_are_sanitized():
    client = AsyncMock()
    provider = OpenAIProvider(Settings(_env_file=None), client)
    client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
    with pytest.raises(InsufficientEvidence):
        await provider.generate("context")
    client.responses.parse.side_effect = APIConnectionError(
        message="secret-key", request=httpx.Request("POST", "https://example.org")
    )
    with pytest.raises(AppError) as exc:
        await provider.generate("context")
    assert exc.value.code == "generation_failed" and "secret-key" not in str(exc.value)
    missing = OpenAIProvider(Settings(_env_file=None, openai_api_key=None))
    with pytest.raises(AppError) as exc:
        await missing.generate("context")
    assert exc.value.code == "ai_not_configured"
