"""Add concept, ai_feedback, confidence_score, difficulty_level to quiz_attempts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quiz_attempts", sa.Column("concept", sa.String(256), nullable=True))
    op.add_column("quiz_attempts", sa.Column("ai_feedback", sa.Text(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("difficulty_level", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("quiz_attempts", "difficulty_level")
    op.drop_column("quiz_attempts", "confidence_score")
    op.drop_column("quiz_attempts", "ai_feedback")
    op.drop_column("quiz_attempts", "concept")
