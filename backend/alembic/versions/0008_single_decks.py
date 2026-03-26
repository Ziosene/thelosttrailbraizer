"""Single deck per type (remove deck_1/deck_2 split)

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    # Add single deck columns
    op.add_column("game_sessions", sa.Column("action_deck", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_deck", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_deck", sa.JSON(), nullable=True))

    # Migrate data: merge deck_1 + deck_2 into single deck (in-progress games will be stale anyway)
    op.execute("""
        UPDATE game_sessions
        SET
            action_deck = COALESCE(action_deck_1, '[]'::json) || COALESCE(action_deck_2, '[]'::json),
            boss_deck   = COALESCE(boss_deck_1,   '[]'::json) || COALESCE(boss_deck_2,   '[]'::json),
            addon_deck  = COALESCE(addon_deck_1,  '[]'::json) || COALESCE(addon_deck_2,  '[]'::json)
    """)

    # Update current_boss_source: deck_1/deck_2 → deck
    op.execute("""
        UPDATE game_players
        SET current_boss_source = 'deck'
        WHERE current_boss_source IN ('deck_1', 'deck_2')
    """)

    # Drop old dual-deck columns
    op.drop_column("game_sessions", "action_deck_1")
    op.drop_column("game_sessions", "action_deck_2")
    op.drop_column("game_sessions", "boss_deck_1")
    op.drop_column("game_sessions", "boss_deck_2")
    op.drop_column("game_sessions", "addon_deck_1")
    op.drop_column("game_sessions", "addon_deck_2")


def downgrade():
    # Re-add dual-deck columns (empty — data not recoverable)
    op.add_column("game_sessions", sa.Column("action_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("action_deck_2", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("boss_deck_2", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_deck_1", sa.JSON(), nullable=True))
    op.add_column("game_sessions", sa.Column("addon_deck_2", sa.JSON(), nullable=True))

    # Split single deck back into two halves (best-effort)
    op.execute("""
        UPDATE game_sessions
        SET
            action_deck_1 = action_deck,
            action_deck_2 = '[]'::json,
            boss_deck_1   = boss_deck,
            boss_deck_2   = '[]'::json,
            addon_deck_1  = addon_deck,
            addon_deck_2  = '[]'::json
    """)

    # Revert current_boss_source: deck → deck_1
    op.execute("""
        UPDATE game_players
        SET current_boss_source = 'deck_1'
        WHERE current_boss_source = 'deck'
    """)

    op.drop_column("game_sessions", "action_deck")
    op.drop_column("game_sessions", "boss_deck")
    op.drop_column("game_sessions", "addon_deck")
