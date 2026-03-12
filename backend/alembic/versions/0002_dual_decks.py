"""Dual decks + market for boss and addon

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── game_sessions: replace single decks with dual decks + market ──────────
    op.add_column("game_sessions", sa.Column("action_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_deck_2", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_discard_2", sa.JSON(), nullable=True))

    op.add_column("game_sessions", sa.Column("boss_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_deck_2", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_market_1", sa.Integer(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_market_2", sa.Integer(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_discard_2", sa.JSON(), nullable=True))

    op.add_column("game_sessions", sa.Column("addon_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_deck_2", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_market_1", sa.Integer(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_market_2", sa.Integer(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_discard_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_discard_2", sa.JSON(), nullable=True))

    # Remove old single-deck columns
    op.drop_column("game_sessions", "action_deck")
    op.drop_column("game_sessions", "action_discard")
    op.drop_column("game_sessions", "boss_deck")
    op.drop_column("game_sessions", "boss_discard")
    op.drop_column("game_sessions", "addon_deck")
    op.drop_column("game_sessions", "addon_discard")

    # ── game_players: track which source the current boss came from ────────────
    op.add_column("game_players", sa.Column("current_boss_source", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("game_players", "current_boss_source")

    op.add_column("game_sessions", sa.Column("action_deck", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_discard", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_deck", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_discard", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_deck", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_discard", sa.JSON(), nullable=True))

    op.drop_column("game_sessions", "action_deck_1")
    op.drop_column("game_sessions", "action_deck_2")
    op.drop_column("game_sessions", "action_discard_1")
    op.drop_column("game_sessions", "action_discard_2")
    op.drop_column("game_sessions", "boss_deck_1")
    op.drop_column("game_sessions", "boss_deck_2")
    op.drop_column("game_sessions", "boss_market_1")
    op.drop_column("game_sessions", "boss_market_2")
    op.drop_column("game_sessions", "boss_discard_1")
    op.drop_column("game_sessions", "boss_discard_2")
    op.drop_column("game_sessions", "addon_deck_1")
    op.drop_column("game_sessions", "addon_deck_2")
    op.drop_column("game_sessions", "addon_market_1")
    op.drop_column("game_sessions", "addon_market_2")
    op.drop_column("game_sessions", "addon_discard_1")
    op.drop_column("game_sessions", "addon_discard_2")
