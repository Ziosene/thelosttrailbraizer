"""Add trophies field to game_players (cert boss cards kept as physical trophies)

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game_players", sa.Column("trophies", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_players", "trophies")
