"""llm_credential client-side encryption columns

Revision ID: a1c9f2b8e4d0
Revises: f1a2b3c4d5e6
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9f2b8e4d0'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    기존 encrypted_key는 서버 마스터키(Fernet)로 암호화된 값이라 새 스킴(클라이언트
    패스프레이즈 유도 AES-GCM)으로 옮길 방법이 없다 — 서버가 대신 패스프레이즈를
    만들어 줄 수 없기 때문(docs/superpowers/specs/2026-08-17-byok-client-side-
    encryption-design.md §6). 기존 행은 폐기하고, 사용자는 새 화면에서 한 번
    재등록해야 한다.
    """
    op.execute("DELETE FROM llm_credential")
    op.add_column('llm_credential', sa.Column('salt', sa.LargeBinary(), nullable=False))
    op.add_column('llm_credential', sa.Column('iv', sa.LargeBinary(), nullable=False))
    op.add_column('llm_credential', sa.Column('kdf_iterations', sa.Integer(), nullable=False))
    op.add_column('llm_credential', sa.Column('masked_key', sa.String(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('llm_credential', 'masked_key')
    op.drop_column('llm_credential', 'kdf_iterations')
    op.drop_column('llm_credential', 'iv')
    op.drop_column('llm_credential', 'salt')
