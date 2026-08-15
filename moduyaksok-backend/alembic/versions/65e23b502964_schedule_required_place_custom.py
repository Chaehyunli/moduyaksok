"""add is_custom/mapx/mapy to schedule_required_place for user-searched places

Revision ID: 65e23b502964
Revises: d2e7a4c1b902
Create Date: 2026-08-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "65e23b502964"
down_revision: Union[str, Sequence[str], None] = "d2e7a4c1b902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_required_place",
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("schedule_required_place", "is_custom", server_default=None)
    # 사용자가 검색해서 직접 고른 장소는 재생성 때 다시 검색해도 표준 카테고리·
    # 태그 쿼리에 안 걸릴 수 있어(naver_local_search.py의 _PLACE_CATEGORIES와
    # 무관한 임의 검색어), place_candidates에 원본 좌표를 직접 주입해야 한다 —
    # 그래서 네이버 검색 원본 형식(mapx/mapy, ×1e7 문자열) 그대로 저장한다.
    # 일반 필수 장소는 매번 새 place_candidates에서 다시 찾아지므로 비워둔다.
    op.add_column(
        "schedule_required_place", sa.Column("mapx", sa.String(), nullable=True)
    )
    op.add_column(
        "schedule_required_place", sa.Column("mapy", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("schedule_required_place", "mapy")
    op.drop_column("schedule_required_place", "mapx")
    op.drop_column("schedule_required_place", "is_custom")
