"""Replace per-deck discards with 3 shared graveyard piles

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Replace action_discard_1/2 with single shared action_discard
    op.add_column("game_sessions", sa.Column("action_discard", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "action_discard_1")
    op.drop_column("game_sessions", "action_discard_2")

    # Replace boss_discard_1/2 with boss_graveyard
    op.add_column("game_sessions", sa.Column("boss_graveyard", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "boss_discard_1")
    op.drop_column("game_sessions", "boss_discard_2")

    # Replace addon_discard_1/2 with addon_graveyard
    op.add_column("game_sessions", sa.Column("addon_graveyard", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "addon_discard_1")
    op.drop_column("game_sessions", "addon_discard_2")


def downgrade() -> None:
    op.add_column("game_sessions", sa.Column("action_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_discard_2", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "action_discard")

    op.add_column("game_sessions", sa.Column("boss_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_discard_2", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "boss_graveyard")

    op.add_column("game_sessions", sa.Column("addon_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_discard_2", sa.JSON(), nullable=True))
    op.drop_column("game_sessions", "addon_graveyard")
