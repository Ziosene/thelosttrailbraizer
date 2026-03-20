"""add game_state column to game_sessions

Revision ID: 0006_game_state
Revises: 0005_combat_state
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_game_state"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_sessions",
        sa.Column("game_state", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("game_sessions", "game_state")
