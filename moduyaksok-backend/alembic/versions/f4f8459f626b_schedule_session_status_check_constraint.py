"""schedule_session status check constraint

Revision ID: f4f8459f626b
Revises: 288e00a4902d
Create Date: 2026-08-07 11:54:01.428940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f4f8459f626b'
down_revision: Union[str, Sequence[str], None] = '288e00a4902d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        'ck_schedule_session_status',
        'schedule_session',
        "status IN ('draft', 'confirmed')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_schedule_session_status', 'schedule_session', type_='check')
