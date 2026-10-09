"""Conversation and Context Engine V3.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def add_missing_columns(table: str, additions: dict[str, sa.Column]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    for name, column in additions.items():
        if name not in existing:
            op.add_column(table, column)


def add_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    add_missing_columns(
        "conversations",
        {
            "last_message_at": sa.Column(
                # SQLite rejects non-constant defaults on ALTER TABLE. New rows are
                # populated by the ORM; existing rows are backfilled just below.
                "last_message_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            "status": sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            "summary": sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            "active_topic": sa.Column(
                "active_topic", sa.String(120), nullable=False, server_default=""
            ),
            "metadata_json": sa.Column(
                "metadata_json", sa.Text(), nullable=False, server_default="{}"
            ),
        },
    )
    op.execute(
        "UPDATE conversations "
        "SET last_message_at = COALESCE(last_message_at, updated_at, created_at, CURRENT_TIMESTAMP)"
    )
    add_index_if_missing("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    add_index_if_missing("ix_conversations_status", "conversations", ["status"])

    add_missing_columns(
        "messages",
        {
            "agent_used": sa.Column("agent_used", sa.String(80), nullable=True),
            "tools_used": sa.Column("tools_used", sa.Text(), nullable=False, server_default="[]"),
            "execution_id": sa.Column("execution_id", sa.String(36), nullable=True),
            "metadata_json": sa.Column(
                "metadata_json", sa.Text(), nullable=False, server_default="{}"
            ),
        },
    )
    add_missing_columns(
        "execution_traces",
        {
            "context_build_ms": sa.Column(
                "context_build_ms", sa.Integer(), nullable=False, server_default="0"
            ),
            "routing_ms": sa.Column("routing_ms", sa.Integer(), nullable=False, server_default="0"),
            "agent_execution_ms": sa.Column(
                "agent_execution_ms", sa.Integer(), nullable=False, server_default="0"
            ),
            "llm_ms": sa.Column("llm_ms", sa.Integer(), nullable=False, server_default="0"),
        },
    )

    if "context_entities" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "context_entities",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.String(36),
                sa.ForeignKey("conversations.id"),
                nullable=False,
            ),
            sa.Column("entity_type", sa.String(80), nullable=False),
            sa.Column("label", sa.String(200), nullable=False, server_default=""),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("source_execution_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_context_entities_conversation_id", "context_entities", ["conversation_id"]
        )
        op.create_index("ix_context_entities_entity_type", "context_entities", ["entity_type"])
        op.create_index("ix_context_entities_status", "context_entities", ["status"])


def downgrade() -> None:
    op.drop_table("context_entities")
    for column in ("llm_ms", "agent_execution_ms", "routing_ms", "context_build_ms"):
        op.drop_column("execution_traces", column)
    for column in ("metadata_json", "execution_id", "tools_used", "agent_used"):
        op.drop_column("messages", column)
    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    for column in ("metadata_json", "active_topic", "summary", "status", "last_message_at"):
        op.drop_column("conversations", column)
