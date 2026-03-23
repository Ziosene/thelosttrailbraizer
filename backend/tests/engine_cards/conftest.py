"""
Fixture condivise per i test delle engine_cards.

Fornisce factory per creare GameSession + GamePlayer in SQLite in-memory,
con carte azione fittizie sufficienti per testare draw, discard, ecc.
"""
import pytest
from app.models.game import GameSession, GamePlayer, GameStatus
from app.models.card import ActionCard, BossCard
from app.models.user import User

# ─── ID offset per le carte test (evita collisioni con carte reali) ────────────
_CARD_ID_OFFSET = 9000
_USER_ID_OFFSET = 9000
_GAME_ID_OFFSET = 9000
_PLAYER_ID_OFFSET = 9000

_counter = {"card": 0, "user": 0, "game": 0, "player": 0}


def _next(kind: str) -> int:
    _counter[kind] += 1
    return globals()[f"_{kind.upper()}_ID_OFFSET"] + _counter[kind]


# ─── Factory ──────────────────────────────────────────────────────────────────

def make_action_card(db, *, card_id: int | None = None, card_type: str = "Utilità") -> ActionCard:
    cid = card_id or _next("card")
    card = ActionCard(
        id=cid, number=cid, name=f"Test Card {cid}",
        card_type=card_type, when="Sempre", effect="Effetto di test",
        rarity="Comune", copies=3,
    )
    db.add(card)
    db.flush()
    return card


def make_boss_card(db, *, boss_id: int | None = None, hp: int = 5, threshold: int = 6) -> BossCard:
    bid = boss_id or _next("card")
    boss = BossCard(
        id=bid, number=bid, name=f"Test Boss {bid}",
        hp=hp, dice_threshold=threshold,
        ability="Nessuna abilità", reward_licenze=2,
        has_certification=False, difficulty="Media",
    )
    db.add(boss)
    db.flush()
    return boss


def make_user(db) -> User:
    uid = _next("user")
    user = User(id=uid, nickname=f"player_{uid}", password_hash="x")
    db.add(user)
    db.flush()
    return user


def make_game(db, *, n_action_cards: int = 30) -> GameSession:
    """Crea una GameSession con mazzi di carte fittizie."""
    # Seed carte azione per il mazzo
    card_ids = []
    for _ in range(n_action_cards):
        c = make_action_card(db)
        card_ids.append(c.id)

    gid = _next("game")
    game = GameSession(
        id=gid, code=f"T{gid:05d}",
        status=GameStatus.in_progress,
        action_deck_1=card_ids[:n_action_cards // 2],
        action_deck_2=card_ids[n_action_cards // 2:],
        action_discard=[],
        boss_deck_1=[], boss_deck_2=[],
        addon_deck_1=[], addon_deck_2=[],
        turn_order=[],
        game_state={},
    )
    db.add(game)
    db.flush()
    return game


def make_player(
    db,
    game: GameSession,
    *,
    seniority: str = "Senior",
    role: str = "Administrator",
    hp: int = 3,
    licenze: int = 5,
    certificazioni: int = 0,
) -> GamePlayer:
    """Crea un GamePlayer e lo associa alla game."""
    user = make_user(db)
    pid = _next("player")
    player = GamePlayer(
        id=pid, game_id=game.id, user_id=user.id,
        seniority=seniority, role=role,
        hp=hp, max_hp=hp, licenze=licenze,
        certificazioni=certificazioni, trophies=[],
        cards_played_this_turn=0, combat_state=None,
        bosses_defeated=0, score=0,
    )
    db.add(player)
    db.flush()
    # Aggiorna turn_order del game
    game.turn_order = (game.turn_order or []) + [player.id]
    db.flush()
    db.refresh(game)
    return player


# ─── Fixture pronte all'uso ───────────────────────────────────────────────────

@pytest.fixture
def game2(db):
    """
    GameSession + 2 giocatori (caster=players[0], target=players[1]).
    La relazione game.players è caricata da SQLAlchemy via lazy load.
    """
    game = make_game(db)
    p1 = make_player(db, game, licenze=5, hp=3)
    p2 = make_player(db, game, licenze=5, hp=3)
    db.refresh(game)
    return game, p1, p2


@pytest.fixture
def game3(db):
    """GameSession + 3 giocatori."""
    game = make_game(db)
    p1 = make_player(db, game, licenze=5, hp=3)
    p2 = make_player(db, game, licenze=5, hp=3)
    p3 = make_player(db, game, licenze=5, hp=3)
    db.refresh(game)
    return game, p1, p2, p3
