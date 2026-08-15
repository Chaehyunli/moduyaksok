"""drop unused feedback_message table

Revision ID: f1a2b3c4d5e6
Revises: 65e23b502964
Create Date: 2026-08-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "65e23b502964"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("feedback_message")


def downgrade() -> None:
    op.create_table(
        "feedback_message",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("session_id", postgresql.UUID(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["schedule_session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
