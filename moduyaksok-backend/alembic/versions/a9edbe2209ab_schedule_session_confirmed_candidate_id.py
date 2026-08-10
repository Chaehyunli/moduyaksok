"""schedule_session confirmed_candidate_id

Revision ID: a9edbe2209ab
Revises: f4f8459f626b
Create Date: 2026-08-10 22:06:57.221727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a9edbe2209ab'
down_revision: Union[str, Sequence[str], None] = 'f4f8459f626b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'schedule_session', sa.Column('confirmed_candidate_id', sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('schedule_session', 'confirmed_candidate_id')
