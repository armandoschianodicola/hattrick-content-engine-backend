from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Topic(BaseModel):
    id: str
    name: str
    description: str


class Document(BaseModel):
    id: str
    title: str
    source_id: str
    source_url: str | None
    authority: Literal["official", "community", "personal", "illustrative"]
    metadata: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document: Document
    text: str
    topic_ids: list[str]
    checksum: str
    score: float = 1.0


class SourceReference(BaseModel):
    chunk_id: str
    document_id: str
    source_id: str
    title: str
    source_url: str | None
    authority: str
    checksum: str
    score: float
