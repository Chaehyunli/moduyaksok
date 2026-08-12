"""persist required schedule places and normalized conditions

Revision ID: d2e7a4c1b902
Revises: b8a2d6c9e301
Create Date: 2026-08-12 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2e7a4c1b902"
down_revision: Union[str, Sequence[str], None] = "b8a2d6c9e301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_session",
        sa.Column(
            "normalized_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("schedule_session", "normalized_conditions", server_default=None)
    op.create_table(
        "schedule_required_place",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("map_url", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["schedule_session.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "place_id", name="uq_schedule_required_place_session_place"),
    )
    op.create_index(
        op.f("ix_schedule_required_place_place_id"),
        "schedule_required_place",
        ["place_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_required_place_place_id"), table_name="schedule_required_place")
    op.drop_table("schedule_required_place")
    op.drop_column("schedule_session", "normalized_conditions")
