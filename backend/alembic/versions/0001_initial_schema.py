"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enum types (PostgreSQL) ---
    rarity_enum = sa.Enum(
        "Comune", "Non comune", "Raro", "Leggendario",
        name="rarity",
    )
    addon_type_enum = sa.Enum("Passivo", "Attivo", name="addontype")
    game_status_enum = sa.Enum("waiting", "in_progress", "finished", name="gamestatus")
    turn_phase_enum = sa.Enum("draw", "action", "combat", "end", name="turnphase")
    seniority_enum = sa.Enum(
        "Junior", "Experienced", "Senior", "Evangelist",
        name="seniority",
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nickname", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("elo_rating", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("games_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    # --- action_cards ---
    op.create_table(
        "action_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("card_type", sa.String(50), nullable=False),
        sa.Column("when", sa.String(200), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="2"),
    )

    # --- boss_cards ---
    op.create_table(
        "boss_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("hp", sa.Integer(), nullable=False),
        sa.Column("dice_threshold", sa.Integer(), nullable=False),
        sa.Column("ability", sa.Text(), nullable=False),
        sa.Column("reward_licenze", sa.Integer(), nullable=False),
        sa.Column("has_certification", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("difficulty", sa.String(20), nullable=False),
    )

    # --- addon_cards ---
    op.create_table(
        "addon_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("addon_type", addon_type_enum, nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("synergy", sa.Text(), nullable=True),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False, server_default="10"),
    )

    # --- game_sessions (winner_id FK added AFTER game_players — circular dep) ---
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(8), nullable=False, unique=True),
        sa.Column("status", game_status_enum, nullable=False, server_default="waiting"),
        sa.Column("max_players", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("current_turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turn_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_phase", turn_phase_enum, nullable=False, server_default="draw"),
        sa.Column("action_deck", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("boss_deck", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("addon_deck", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("action_discard", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("boss_discard", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("addon_discard", sa.JSON(), nullable=False, server_default="'[]'"),
        sa.Column("turn_order", sa.JSON(), nullable=False, server_default="'[]'"),
        # winner_id: NULL until game ends — FK added below after game_players exists
        sa.Column("winner_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )

    # --- game_players ---
    op.create_table(
        "game_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("game_sessions.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seniority", seniority_enum, nullable=False),
        sa.Column("role", sa.String(100), nullable=False),
        sa.Column("hp", sa.Integer(), nullable=False),
        sa.Column("max_hp", sa.Integer(), nullable=False),
        sa.Column("licenze", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("certificazioni", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cards_played_this_turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_in_combat", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("current_boss_id", sa.Integer(), sa.ForeignKey("boss_cards.id"), nullable=True),
        sa.Column("current_boss_hp", sa.Integer(), nullable=True),
        sa.Column("combat_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bosses_defeated", sa.Integer(), nullable=False, server_default="0"),
    )

    # --- Add winner_id FK now that game_players exists ---
    op.create_foreign_key(
        "fk_game_sessions_winner_id",
        "game_sessions",
        "game_players",
        ["winner_id"],
        ["id"],
        use_alter=True,
    )

    # --- player_addons ---
    op.create_table(
        "player_addons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("game_players.id"), nullable=False),
        sa.Column("addon_id", sa.Integer(), sa.ForeignKey("addon_cards.id"), nullable=False),
        sa.Column("is_tapped", sa.Boolean(), nullable=False, server_default="false"),
    )

    # --- player_hand_cards ---
    op.create_table(
        "player_hand_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("game_players.id"), nullable=False),
        sa.Column("action_card_id", sa.Integer(), sa.ForeignKey("action_cards.id"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("player_hand_cards")
    op.drop_table("player_addons")
    op.drop_constraint("fk_game_sessions_winner_id", "game_sessions", type_="foreignkey")
    op.drop_table("game_players")
    op.drop_table("game_sessions")
    op.drop_table("addon_cards")
    op.drop_table("boss_cards")
    op.drop_table("action_cards")
    op.drop_table("users")

    sa.Enum(name="seniority").drop(op.get_bind())
    sa.Enum(name="turnphase").drop(op.get_bind())
    sa.Enum(name="gamestatus").drop(op.get_bind())
    sa.Enum(name="addontype").drop(op.get_bind())
    sa.Enum(name="rarity").drop(op.get_bind())
