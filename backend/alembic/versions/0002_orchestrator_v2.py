"""Orchestrator V2 state and execution traces.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("pending_actions")}
    additions = {
        "conversation_id": sa.Column("conversation_id", sa.String(36), nullable=True),
        "agent_id": sa.Column("agent_id", sa.String(80), nullable=True),
        "tool_name": sa.Column("tool_name", sa.String(120), nullable=True),
        "status": sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        "created_at": sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("pending_actions", column)

    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("pending_actions")}
    if "ix_pending_actions_conversation_id" not in existing_indexes:
        op.create_index(
            "ix_pending_actions_conversation_id", "pending_actions", ["conversation_id"]
        )
    if "ix_pending_actions_status" not in existing_indexes:
        op.create_index("ix_pending_actions_status", "pending_actions", ["status"])

    table_names = set(sa.inspect(bind).get_table_names())
    if "execution_traces" not in table_names:
        op.create_table(
            "execution_traces",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
            ),
            sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=True),
            sa.Column("intent", sa.String(120), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("route_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("plan_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("results_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("agents_used", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("tools_used", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_execution_traces_conversation_id", "execution_traces", ["conversation_id"]
        )
        op.create_index("ix_execution_traces_intent", "execution_traces", ["intent"])
        op.create_index("ix_execution_traces_status", "execution_traces", ["status"])
    if "agent_runtime_states" not in table_names:
        op.create_table(
            "agent_runtime_states",
            sa.Column("agent_id", sa.String(80), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "skill_runtime_states" not in table_names:
        op.create_table(
            "skill_runtime_states",
            sa.Column("skill_id", sa.String(80), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("skill_runtime_states")
    op.drop_table("agent_runtime_states")
    op.drop_index("ix_execution_traces_status", table_name="execution_traces")
    op.drop_index("ix_execution_traces_intent", table_name="execution_traces")
    op.drop_index("ix_execution_traces_conversation_id", table_name="execution_traces")
    op.drop_table("execution_traces")
    with op.batch_alter_table("pending_actions") as batch:
        batch.drop_index("ix_pending_actions_status")
        batch.drop_index("ix_pending_actions_conversation_id")
        batch.drop_column("created_at")
        batch.drop_column("status")
        batch.drop_column("tool_name")
        batch.drop_column("agent_id")
        batch.drop_column("conversation_id")
