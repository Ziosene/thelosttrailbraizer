"""Add combat_state fields to game_players and tracking fields to game_sessions

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GamePlayer: per-combat transient state (resurrection flags, petrified cards, etc.)
    op.add_column("game_players", sa.Column("combat_state", sa.JSON(), nullable=True))
    # GamePlayer: addon cost penalty queued by boss 26 (CPQ Configuration Chaos)
    op.add_column(
        "game_players",
        sa.Column("pending_addon_cost_penalty", sa.Integer(), nullable=True, server_default="0"),
    )
    # GameSession: last boss defeated (used by boss 55 mimic and boss 74 shape shifter)
    op.add_column("game_sessions", sa.Column("last_defeated_boss_id", sa.Integer(), nullable=True))
    # GameSession: last legendary (cert) boss defeated (used by boss 100 omega)
    op.add_column(
        "game_sessions",
        sa.Column("last_defeated_legendary_boss_id", sa.Integer(), nullable=True),
    )
    # GameSession: card IDs permanently banned by boss 56 (Change Data Capture Lurker)
    op.add_column("game_sessions", sa.Column("banned_card_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_players", "combat_state")
    op.drop_column("game_players", "pending_addon_cost_penalty")
    op.drop_column("game_sessions", "last_defeated_boss_id")
    op.drop_column("game_sessions", "last_defeated_legendary_boss_id")
    op.drop_column("game_sessions", "banned_card_ids")
