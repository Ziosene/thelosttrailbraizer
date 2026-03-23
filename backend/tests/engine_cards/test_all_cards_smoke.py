"""
Smoke test per TUTTE le 300 carte azione.

Ogni carta viene chiamata in uno scenario "happy path" (condizioni favorevoli):
- giocatore fuori dal combattimento con licenze e carte in mano
- target presente con licenze, HP, carte in mano e addon
- mazzi pieni

Il test fallisce se la carta:
  1. Lancia un'eccezione (bug implementativo)
  2. Restituisce applied=False in happy-path (effetto silenziosamente ignorato)
  3. Non restituisce un dizionario (return type sbagliato)

I casi ESCLUSI sono specificati per carta nel dizionario KNOWN_SKIP.
Run: pytest tests/engine_cards/test_all_cards_smoke.py -v
"""
import pytest
from sqlalchemy.orm import Session

from app.game.engine_cards import apply_action_card_effect
from app.models.card import ActionCard, AddonCard
from app.models.game import GamePlayer, PlayerHandCard, PlayerAddon

from tests.engine_cards.conftest import make_game, make_player, make_action_card, make_boss_card


# ─── Carte che hanno motivi legittimi per applied=False in happy-path ──────────
# Formato: card_number -> motivo skip
KNOWN_SKIP: dict[int, str] = {
    # ── Effetti passivi (non applicabili tramite apply_action_card_effect) ──
    57: "api proxy — effetto passivo (blocca carte avversario)",
    74: "routing configuration — effetto passivo",
    77: "kafka connector — effetto passivo (flag in combat_state)",

    # ── Carte che richiedono is_in_combat=True (caster) ──
    5:   "solo in combattimento",
    6:   "solo in combattimento",
    9:   "solo in combattimento",
    10:  "solo in combattimento",
    11:  "solo in combattimento",
    12:  "solo in combattimento",
    13:  "solo in combattimento",
    14:  "solo in combattimento",
    15:  "solo in combattimento",
    16:  "solo in combattimento",
    21:  "solo in combattimento",
    22:  "solo in combattimento",
    26:  "solo in combattimento",
    27:  "solo in combattimento",
    28:  "solo in combattimento",
    29:  "solo in combattimento",
    30:  "solo in combattimento",
    34:  "solo in combattimento",
    38:  "solo in combattimento",
    39:  "solo in combattimento",
    49:  "solo in combattimento",
    50:  "solo in combattimento",
    51:  "solo in combattimento",
    52:  "solo in combattimento",
    53:  "solo in combattimento",
    54:  "solo in combattimento",
    55:  "solo in combattimento",
    58:  "solo in combattimento",
    59:  "solo in combattimento",
    60:  "solo in combattimento",
    61:  "solo in combattimento",
    62:  "solo in combattimento",
    89:  "solo in combattimento",
    90:  "solo in combattimento",
    91:  "solo in combattimento",
    92:  "solo in combattimento",
    95:  "solo in combattimento",
    96:  "solo in combattimento",
    97:  "solo in combattimento",
    101: "solo in combattimento",
    102: "solo in combattimento",
    103: "solo in combattimento",
    104: "solo in combattimento",
    105: "solo in combattimento",
    126: "solo in combattimento",
    127: "solo in combattimento",
    128: "solo in combattimento",
    129: "solo in combattimento",
    130: "solo in combattimento",
    131: "solo in combattimento",
    132: "solo in combattimento",
    133: "solo in combattimento",
    134: "solo in combattimento",
    135: "solo in combattimento",
    136: "solo in combattimento",
    141: "solo in combattimento",
    142: "solo in combattimento",
    143: "solo in combattimento",
    144: "solo in combattimento",
    145: "solo in combattimento",
    146: "solo in combattimento",
    147: "solo in combattimento",
    148: "solo in combattimento",
    149: "solo in combattimento",
    150: "solo in combattimento",
    151: "solo in combattimento",
    156: "solo in combattimento",
    169: "solo in combattimento",
    170: "solo in combattimento",
    171: "solo in combattimento",
    191: "solo in combattimento",
    192: "solo in combattimento",
    195: "solo in combattimento",
    203: "solo in combattimento",
    204: "solo in combattimento",
    216: "solo in combattimento",
    218: "solo in combattimento",
    224: "solo in combattimento",
    228: "solo in combattimento",
    231: "solo in combattimento",
    233: "solo in combattimento",
    240: "solo in combattimento",
    261: "solo in combattimento",
    281: "solo in combattimento",

    # ── Carte che richiedono il TARGET in combattimento ──
    72:  "target deve essere in combattimento",
    75:  "target deve essere in combattimento",
    98:  "target deve essere in combattimento",

    # ── Carte di reazione (giocabili solo in risposta) ──
    78:  "reaction only — giocabile solo come risposta a una carta avversaria",

    # ── Carte che richiedono scarti nel mazzo ──
    69:  "discard_empty — richiede carte negli scarti",
    174: "discard_empty — richiede carte negli scarti",
    177: "discard_empty — richiede carte negli scarti",
    217: "discard_empty — richiede carte negli scarti",
    243: "empty_discard — richiede carte negli scarti",
    250: "empty_discard — richiede carte negli scarti",

    # ── Condizioni speciali di gioco ──
    100: "usa target_player_id come selettore tipo (1/2/3) anziché ID giocatore",
    209: "streak_too_low — richiede streak di turni consecutivi",
    254: "need_2_different_types — richiede 2 tipi diversi di carte in mano",
    255: "no_certifications — richiede certificazioni nel mazzo scarti",
}

# Carte che richiedono il combattimento (is_in_combat=True) per funzionare
COMBAT_ONLY: set[int] = {
    5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 21, 22, 26, 27, 28, 29, 30, 34, 38, 39,
    49, 50, 51, 52, 53, 54, 55, 58, 59, 60, 61, 62, 89, 90, 91, 92, 95, 96, 97,
    101, 102, 103, 104, 105, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135,
    136, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 156, 169, 170,
    171, 191, 192, 195, 203, 204, 216, 218, 224, 228, 231, 233, 240, 261, 281,
}


def _make_full_player(db, game, *, licenze: int = 10, hp: int = 3, with_addon: bool = True) -> GamePlayer:
    """Crea un giocatore con mano piena e addon."""
    player = make_player(db, game, licenze=licenze, hp=hp)

    # Aggiungi 5 carte in mano
    for _ in range(5):
        card = make_action_card(db)
        db.add(PlayerHandCard(player_id=player.id, action_card_id=card.id))

    # Aggiungi 2 addon
    if with_addon:
        for i in range(2):
            addon_num = 9000 + player.id * 10 + i
            addon = AddonCard(
                id=addon_num, number=addon_num,
                name=f"Test Addon {addon_num}",
                addon_type="Passivo", effect="Nessun effetto",
                cost=5, rarity="Comune",
            )
            db.add(addon)
            db.flush()
            db.add(PlayerAddon(player_id=player.id, addon_id=addon.id))

    db.flush()
    db.refresh(player)
    return player


def _make_card(db, number: int) -> ActionCard:
    """Recupera la carta reale dal DB (seeded in conftest) o ne crea una fittizia."""
    existing = db.query(ActionCard).filter_by(number=number).first()
    if existing:
        return existing
    # Carta non in DB (test senza seed) — crea stub
    stub = ActionCard(
        id=90000 + number, number=number,
        name=f"Stub Card {number}",
        card_type="Utilità", when="Sempre",
        effect="Stub", rarity="Comune", copies=1,
    )
    db.add(stub)
    db.flush()
    return stub


def _game_with_boss(db, *, n_bosses: int = 4) -> tuple:
    """Crea un game con boss nei mazzi."""
    game = make_game(db, n_action_cards=40)
    boss_ids = []
    for i in range(n_bosses):
        b = make_boss_card(db, hp=4, threshold=6)
        boss_ids.append(b.id)
    game.boss_deck_1 = boss_ids[:2]
    game.boss_deck_2 = boss_ids[2:]
    # Addon nei mazzi
    addon_ids = []
    for i in range(6):
        num = 8000 + i
        a = AddonCard(id=num, number=num, name=f"Market Addon {num}",
                      addon_type="Passivo", effect="X", cost=5, rarity="Comune")
        db.add(a)
        db.flush()
        addon_ids.append(a.id)
    game.addon_deck_1 = addon_ids[:3]
    game.addon_deck_2 = addon_ids[3:]
    db.flush()
    db.refresh(game)
    return game


# ─── Parametrizzazione: tutte le carte 1–300 ──────────────────────────────────

ALL_CARD_NUMBERS = list(range(1, 301))


@pytest.mark.parametrize("card_number", ALL_CARD_NUMBERS)
def test_card_smoke_happy_path(card_number, db):
    """
    Ogni carta deve applicarsi senza crash e senza applied=False
    in condizioni favorevoli (target presente, mano piena, addon disponibili).
    """
    if card_number in KNOWN_SKIP:
        pytest.skip(KNOWN_SKIP[card_number])

    game = _game_with_boss(db)

    caster = _make_full_player(db, game, licenze=15, with_addon=True)
    target = _make_full_player(db, game, licenze=10, with_addon=True)

    db.refresh(game)
    db.flush()

    card = _make_card(db, card_number)

    try:
        result = apply_action_card_effect(
            card, caster, game, db,
            target_player_id=target.id,
        )
    except Exception as exc:
        pytest.fail(f"Carta {card_number} ha lanciato un'eccezione: {exc}")

    assert isinstance(result, dict), (
        f"Carta {card_number}: il risultato deve essere un dict, ricevuto {type(result)}"
    )

    applied = result.get("applied")
    status = result.get("status")

    # pending_choice è un successo (la carta chiede input al giocatore)
    if status == "pending_choice":
        assert "choice_type" in result, f"Carta {card_number}: pending_choice senza choice_type"
        assert "card_number" in result, f"Carta {card_number}: pending_choice senza card_number"
        return

    assert applied is not False, (
        f"Carta {card_number} ({card.name}): applied=False in happy-path. "
        f"Motivo: {result.get('reason', result.get('blocked_by', 'sconosciuto'))}. "
        f"Aggiungi la carta a KNOWN_SKIP se questo è il comportamento corretto."
    )


@pytest.mark.parametrize("card_number", ALL_CARD_NUMBERS)
def test_card_no_target_does_not_crash(card_number, db):
    """
    Con target_player_id=None, la carta non deve crashare.
    Può restituire applied=False, ma non deve lanciare eccezioni.
    """
    if card_number in KNOWN_SKIP:
        pytest.skip(KNOWN_SKIP[card_number])

    game = _game_with_boss(db)
    caster = _make_full_player(db, game, licenze=15, with_addon=True)
    db.refresh(game)

    card = _make_card(db, card_number)

    try:
        result = apply_action_card_effect(card, caster, game, db, target_player_id=None)
    except Exception as exc:
        pytest.fail(f"Carta {card_number} senza target ha crashato: {exc}")

    assert isinstance(result, dict), (
        f"Carta {card_number}: il risultato senza target deve essere un dict"
    )


@pytest.mark.parametrize("card_number", ALL_CARD_NUMBERS)
def test_card_target_no_addons(card_number, db):
    """
    Con target senza addon, la carta non deve crashare.
    Se applied=False con reason=target_has_no_addons, è accettabile.
    """
    if card_number in KNOWN_SKIP:
        pytest.skip(KNOWN_SKIP[card_number])

    game = _game_with_boss(db)
    caster = _make_full_player(db, game, licenze=15, with_addon=True)
    target = _make_full_player(db, game, licenze=10, with_addon=False)  # niente addon
    db.refresh(game)

    card = _make_card(db, card_number)

    try:
        result = apply_action_card_effect(card, caster, game, db, target_player_id=target.id)
    except Exception as exc:
        pytest.fail(f"Carta {card_number} con target senza addon ha crashato: {exc}")

    assert isinstance(result, dict)
