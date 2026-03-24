"""add is_eliminated to game_players

Revision ID: 0007_is_eliminated
Revises: 0006_game_state
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_is_eliminated"
down_revision = "0006_game_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_players",
        sa.Column("is_eliminated", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("game_players", "is_eliminated")
