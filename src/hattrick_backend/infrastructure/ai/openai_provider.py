from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, ValidationError

from hattrick_backend.application.prompts.educational_post import SYSTEM_PROMPT
from hattrick_backend.core.exceptions import AppError, InsufficientEvidence
from hattrick_backend.schemas.posts import Content


class GenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")
    sufficient_evidence: bool
    content: Content | None


@dataclass
class AIResult:
    response: GenerationResponse
    model: str
    usage: dict


class AIProvider(Protocol):
    async def generate(self, prompt: str) -> AIResult: ...


class OpenAIProvider:
    def __init__(self, settings, client: AsyncOpenAI | None = None):
        self.settings = settings
        self.client = client

    def _client(self):
        if self.client is None:
            if not self.settings.openai_api_key:
                raise AppError("ai_not_configured", "OpenAI credentials are not configured", 503)
            self.client = AsyncOpenAI(
                api_key=self.settings.openai_api_key.get_secret_value(),
                timeout=self.settings.http_timeout_seconds,
                max_retries=1,
            )
        return self.client

    async def close(self):
        if self.client:
            await self.client.close()

    async def generate(self, prompt):
        kwargs = {}
        # Omit temperature by default; some reasoning models do not accept it.
        if self.settings.openai_temperature is not None:
            kwargs["temperature"] = self.settings.openai_temperature
        try:
            result = await self._client().responses.parse(
                model=self.settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                text_format=GenerationResponse,
                max_output_tokens=self.settings.openai_max_output_tokens,
                store=False,
                **kwargs,
            )
            if result.output_parsed is None:
                raise InsufficientEvidence()
            return AIResult(
                result.output_parsed,
                result.model,
                result.usage.model_dump() if result.usage else {},
            )
        except (OpenAIError, ValidationError):
            raise AppError(
                "generation_failed", "AI generation failed or returned invalid content", 502
            ) from None

    async def embed(self, query):
        try:
            response = await self._client().embeddings.create(
                model=self.settings.embedding_model,
                input=query,
                dimensions=self.settings.embedding_dimensions,
            )
            return response.data[0].embedding
        except OpenAIError:
            raise AppError("embedding_failed", "Query embedding failed", 502) from None
