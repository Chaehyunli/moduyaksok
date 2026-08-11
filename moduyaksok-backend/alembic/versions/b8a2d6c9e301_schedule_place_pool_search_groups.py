"""store schedule place-pool search groups

Revision ID: b8a2d6c9e301
Revises: c24bd64ba972
Create Date: 2026-08-11 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8a2d6c9e301"
down_revision: Union[str, Sequence[str], None] = "c24bd64ba972"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_place_pool",
        sa.Column(
            "search_groups",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("schedule_place_pool", "search_groups", server_default=None)


def downgrade() -> None:
    op.drop_column("schedule_place_pool", "search_groups")
