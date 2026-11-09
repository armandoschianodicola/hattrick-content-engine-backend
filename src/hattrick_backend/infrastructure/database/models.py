from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        schema="backend",
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


Json = JSON().with_variant(JSONB(), "postgresql")


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[str] = mapped_column(String(120), index=True)
    state: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(default=1)
    approved_revision: Mapped[int | None]
    content: Mapped[dict] = mapped_column(Json)
    target_platforms: Mapped[list] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"), unique=True)
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(50))
    options: Mapped[dict] = mapped_column(Json)
    usage: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PostSource(Base):
    __tablename__ = "post_sources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(200))
    provenance: Mapped[dict] = mapped_column(Json)
    __table_args__ = (UniqueConstraint("post_id", "chunk_id"),)


class PostRevision(Base):
    __tablename__ = "post_revisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"))
    revision: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(Json)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("post_id", "revision"),)


class ApprovalEvent(Base):
    __tablename__ = "approval_history"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    revision: Mapped[int]
    actor: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"), index=True)
    revision: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(250), unique=True)
    media_type: Mapped[str] = mapped_column(String(80), default="image/png")
    width: Mapped[int]
    height: Mapped[int]
    theme: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlatformPublication(Base):
    __tablename__ = "platform_publications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"))
    platform: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("post_id", "platform"),)


class PublicationAttempt(Base):
    __tablename__ = "publication_attempts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("backend.posts.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    revision: Mapped[int]
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(250))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("post_id", "platform", "idempotency_key"),
        Index("ix_publication_attempts_status_started", "status", "started_at"),
    )
