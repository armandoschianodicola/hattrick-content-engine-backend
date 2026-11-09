"""Initial backend-owned content schema. Never changes ingestion-owned tables."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def uid():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def post_fk():
    return sa.Column("post_id", sa.Uuid(), sa.ForeignKey("backend.posts.id"), nullable=False)


def timestamp(name="created_at", nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table(
        "posts",
        uid(),
        sa.Column("topic_id", sa.String(120), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("approved_revision", sa.Integer(), nullable=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("target_platforms", JSONB(), nullable=False),
        timestamp(),
        timestamp("updated_at"),
        timestamp("scheduled_at", True),
        schema="backend",
    )
    for column in ("topic_id", "state", "created_at", "scheduled_at"):
        op.create_index(f"ix_posts_{column}", "posts", [column], schema="backend")
    op.create_table(
        "generations",
        uid(),
        post_fk(),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("options", JSONB(), nullable=False),
        sa.Column("usage", JSONB(), nullable=False),
        timestamp(),
        sa.UniqueConstraint("post_id"),
        schema="backend",
    )
    op.create_table(
        "post_sources",
        uid(),
        post_fk(),
        sa.Column("chunk_id", sa.String(200), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
        sa.UniqueConstraint("post_id", "chunk_id"),
        schema="backend",
    )
    op.create_table(
        "post_revisions",
        uid(),
        post_fk(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        timestamp(),
        sa.UniqueConstraint("post_id", "revision"),
        schema="backend",
    )
    op.create_table(
        "approval_history",
        uid(),
        post_fk(),
        sa.Column("from_state", sa.String(30), nullable=False),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        timestamp(),
        schema="backend",
    )
    op.create_table(
        "assets",
        uid(),
        post_fk(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(250), nullable=False, unique=True),
        sa.Column("media_type", sa.String(80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("theme", JSONB(), nullable=False),
        timestamp(),
        schema="backend",
    )
    op.create_table(
        "platform_publications",
        uid(),
        post_fk(),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        timestamp("updated_at"),
        sa.UniqueConstraint("post_id", "platform"),
        schema="backend",
    )
    op.create_table(
        "publication_attempts",
        uid(),
        post_fk(),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(250), nullable=True),
        timestamp("started_at"),
        timestamp("completed_at", True),
        sa.UniqueConstraint("post_id", "platform", "idempotency_key"),
        schema="backend",
    )
    for table in ("post_sources", "approval_history", "assets", "publication_attempts"):
        op.create_index(f"ix_{table}_post_id", table, ["post_id"], schema="backend")
    op.create_index(
        "ix_publication_attempts_status_started",
        "publication_attempts",
        ["status", "started_at"],
        schema="backend",
    )


def downgrade():
    for table in (
        "publication_attempts",
        "platform_publications",
        "assets",
        "approval_history",
        "post_revisions",
        "post_sources",
        "generations",
        "posts",
    ):
        op.drop_table(table, schema="backend")
