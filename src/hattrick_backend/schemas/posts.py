from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from hattrick_backend.domain.enums import Platform, PostState
from hattrick_backend.schemas.knowledge import SourceReference

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")
    title: Text = Field(max_length=140)
    explanation: Text = Field(max_length=600)
    body: Text = Field(max_length=4000)
    key_takeaway: Text = Field(max_length=500)
    caption: Text = Field(max_length=1000)
    hashtags: list[Text] = Field(max_length=15)
    source_chunk_ids: list[Text] = Field(min_length=1, max_length=20)
    related_topic_ids: list[Text] = Field(max_length=10)
    visual_text: str | None = Field(max_length=400)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: Text = Field(max_length=120)
    content_type: Annotated[str, StringConstraints(pattern="^educational$")] = "educational"
    target_platforms: list[Platform] = Field(
        default=[Platform.TELEGRAM], min_length=1, max_length=3
    )
    tone: Text = Field(default="informative", max_length=80)
    language: Text = Field(default="en", max_length=30)
    query: Text | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def unique_platforms(self):
        if len(set(self.target_platforms)) != len(self.target_platforms):
            raise ValueError("target_platforms must be unique")
        return self


class PostEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    content: Content


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class ScheduleRequest(ReviewAction):
    scheduled_at: datetime


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platforms: list[Platform] = Field(min_length=1, max_length=3)
    idempotency_key: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,100}$")]

    @model_validator(mode="after")
    def unique_platforms(self):
        if len(set(self.platforms)) != len(self.platforms):
            raise ValueError("platforms must be unique")
        return self


class PostView(BaseModel):
    id: UUID
    topic_id: str
    state: PostState
    revision: int
    approved_revision: int | None
    content: Content
    target_platforms: list[Platform]
    source_references: list[SourceReference]
    generation: dict
    created_at: datetime
    updated_at: datetime
    scheduled_at: datetime | None


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    background: str = Field(default="#24732D", pattern=r"^#[0-9A-Fa-f]{6}$")
    foreground: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(default="#FFCC00", pattern=r"^#[0-9A-Fa-f]{6}$")
    branding: str = Field(default="Hattrick Learning", max_length=60)
