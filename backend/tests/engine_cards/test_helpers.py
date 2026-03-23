"""
Test per le funzioni helper condivise dalle engine_cards.

- get_target: auto-selezione in 2-player, None in 3+ senza target esplicito
"""
from app.game.engine_cards.helpers import get_target
from tests.engine_cards.conftest import make_game, make_player


def test_get_target_2player_auto_selects(db):
    """In 2 giocatori, get_target auto-seleziona l'unico avversario."""
    game = make_game(db)
    p1 = make_player(db, game)
    p2 = make_player(db, game)
    db.refresh(game)

    result = get_target(game, p1, target_player_id=None)
    assert result is not None
    assert result.id == p2.id


def test_get_target_3player_no_auto(db):
    """In 3+ giocatori, senza target esplicito ritorna None."""
    game = make_game(db)
    p1 = make_player(db, game)
    make_player(db, game)
    make_player(db, game)
    db.refresh(game)

    result = get_target(game, p1, target_player_id=None)
    assert result is None


def test_get_target_explicit_3player(db):
    """Con target_player_id esplicito funziona anche in 3+ giocatori."""
    game = make_game(db)
    p1 = make_player(db, game)
    p2 = make_player(db, game)
    make_player(db, game)
    db.refresh(game)

    result = get_target(game, p1, target_player_id=p2.id)
    assert result is not None
    assert result.id == p2.id


def test_get_target_cannot_target_self(db):
    """Non si può targettare se stessi."""
    game = make_game(db)
    p1 = make_player(db, game)
    db.refresh(game)

    result = get_target(game, p1, target_player_id=p1.id)
    assert result is None


def test_get_target_invalid_id(db):
    """ID inesistente → None."""
    game = make_game(db)
    p1 = make_player(db, game)
    db.refresh(game)

    result = get_target(game, p1, target_player_id=99999)
    assert result is None
