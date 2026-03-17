# The Lost Trailbraizer — Backend Documentation

> Aggiornato automaticamente ad ogni sessione di sviluppo.
> Fonte di verità su architettura, stato di avanzamento e TODO.

---

## Indice

1. [Stack & Setup](#1-stack--setup)
2. [Struttura del progetto](#2-struttura-del-progetto)
3. [Architettura generale](#3-architettura-generale)
4. [Database — Modelli](#4-database--modelli)
5. [API REST](#5-api-rest)
6. [WebSocket — Protocollo](#6-websocket--protocollo)
7. [Game Engine](#7-game-engine)
8. [Flusso di gioco](#8-flusso-di-gioco)
9. [Stato di avanzamento](#9-stato-di-avanzamento)
10. [TODO e prossimi passi](#10-todo-e-prossimi-passi)

---

## 1. Stack & Setup

| Componente   | Tecnologia                          |
|-------------|-------------------------------------|
| Framework   | FastAPI 0.115                       |
| WebSocket   | Starlette (integrato in FastAPI)    |
| ORM         | SQLAlchemy 2.0 (Mapped / mapped_column) |
| Migrations  | Alembic 1.13                        |
| Database    | PostgreSQL (psycopg2-binary)        |
| Auth        | JWT via python-jose + passlib/bcrypt |
| Config      | pydantic-settings (legge `.env`)    |
| Server      | Uvicorn                             |

### Avvio locale

```bash
# 1. Crea e attiva virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Installa dipendenze
pip install -r requirements.txt

# 3. Configura variabili d'ambiente
cp .env.example .env
# → modifica DATABASE_URL e SECRET_KEY

# 4. Crea il database e applica le migrazioni
alembic upgrade head

# 5. (Opzionale) Carica le carte dal markdown
# → script da creare: python scripts/seed_cards.py

# 6. Avvia il server
uvicorn app.main:app --reload
```

### Avvio con Docker Compose (consigliato)

```bash
# 1. Copia il file .env
cp backend/.env.example backend/.env
# → modifica SECRET_KEY

# 2. Avvia tutto (postgres + backend + migrations + seed automatici)
docker compose up --build
```

Il server sarà disponibile su `http://localhost:8000`.
Le migrazioni Alembic e il seed delle carte vengono eseguiti automaticamente al primo avvio.

### Variabili d'ambiente (`.env`)

```
DATABASE_URL=postgresql://user:password@localhost:5432/trailbraizer
SECRET_KEY=<random 32+ char string>
ACCESS_TOKEN_EXPIRE_MINUTES=10080   # 7 giorni
```

---

## 2. Struttura del progetto

```
backend/
├── requirements.txt              ✅ include pytest + pytest-asyncio
├── .env.example                  ✅
├── alembic.ini                   ✅
├── pytest.ini                    ✅
├── alembic/
│   ├── env.py                    ✅ configurato
│   ├── script.py.mako            ✅
│   └── versions/
│       ├── 0001_initial_schema.py ✅ schema completo + FK circolare risolta
│       ├── 0002_dual_decks.py    ✅ doppi mazzi + mercato
│       ├── 0003_shared_discards.py ✅ 3 scarti condivisi
│       ├── 0004_player_trophies.py ✅ trofei boss cert
│       └── 0005_combat_state.py  ✅ combat_state, pending_addon_cost_penalty, last_defeated_boss_id, banned_card_ids
├── app/
│   ├── __init__.py               ✅
│   ├── main.py                   ✅ FastAPI app + WebSocket endpoint + auth JWT
│   ├── config.py                 ✅ Settings da .env
│   ├── database.py               ✅ engine, SessionLocal, Base
│   ├── auth.py                   ✅ JWT, hash password, get_current_user
│   ├── models/
│   │   ├── __init__.py           ✅ importa tutti i modelli (per Alembic autogenerate)
│   │   ├── user.py               ✅ User
│   │   ├── card.py               ✅ ActionCard, BossCard, AddonCard
│   │   └── game.py               ✅ GameSession, GamePlayer, PlayerAddon, PlayerHandCard
│   ├── schemas/
│   │   ├── __init__.py           ✅
│   │   ├── user.py               ✅ UserRegister, UserLogin, TokenResponse, UserPublic
│   │   └── game.py               ✅ CreateGame, GameInfo, PlayerState, GameState
│   ├── api/
│   │   ├── __init__.py           ✅
│   │   └── routes/
│   │       ├── __init__.py       ✅
│   │       ├── auth.py           ✅ POST /register, POST /login, GET /me
│   │       ├── users.py          ✅ GET /leaderboard, GET /{nickname}
│   │       └── games.py          ✅ GET /games (lobby), POST /games, GET /games/{code}
│   ├── websocket/
│   │   ├── __init__.py           ✅
│   │   ├── events.py             ✅ ClientAction / ServerEvent (classi con costanti)
│   │   ├── manager.py            ✅ ConnectionManager (rooms per game_code)
│   │   ├── game_helpers.py       ✅ helper condivisi (_build_game_state, _error, _broadcast_state, _apply_elo, …)
│   │   ├── game_handler.py       ✅ thin router WS (65 righe) — importa da handlers/
│   │   └── handlers/
│   │       ├── __init__.py       ✅
│   │       ├── lobby.py          ✅ _handle_join, _handle_select_character, _handle_start_game
│   │       ├── turn.py           ✅ _handle_draw_card, _handle_play_card, _handle_buy_addon, _handle_use_addon, _handle_end_turn
│   │       └── combat.py         ✅ _handle_start_combat, _handle_roll_dice, _handle_retreat, _handle_declare_card, _handle_declare_card_type
│   └── game/
│       ├── __init__.py           ✅
│       ├── engine.py             ✅ funzioni pure core (~165 righe): roll, combat, deck, death, ELO + re-export engine_boss
│       ├── engine_boss.py        ✅ boss ability system (~1000 righe): tutti i 100 boss, query helper, apply_boss_ability
│       └── engine_cards/         ✅ effetti carte azione (300/300 implementate)
│           ├── __init__.py       ✅ dispatcher apply_action_card_effect
│           ├── helpers.py        ✅ get_target()
│           ├── economica.py      ✅ carte 1–8, 41–48, 81–88, 121–125, 159–168, 208–214, 230, 235, 241, 244, 251–257
│           ├── offensiva.py      ✅ carte 9–18, 49–54, 89–95, 126–130, 141–150, 191–195, 228, 231, 233, 240, 261–262
│           ├── difensiva.py      ✅ carte 19–25, 55–58, 96–100, 131–135, 151–158, 201–207, 258–260
│           ├── manipolazione.py  ✅ carte 26–30, 59–62, 101–105, 136, 169–171, 216–220
│           ├── utilita.py        ✅ carte 31–37, 63–69, 80, 106–110, 137–138, 172–180, 196–200, 215, 221, 223, 226–227, 232, 234, 238–239, 242–243, 245, 247–250, 263–267, 269–270, 282–284, 287, 289, 291, 299
│           └── interferenza.py   ✅ carte 38–40, 70–79, 111–120, 139–140, 181–190, 222, 224–225, 229, 236–237, 246, 268
├── scripts/
│   └── seed_cards.py             ✅ parser .md → insert DB (idempotente, safe re-run)
└── tests/
    ├── __init__.py               ✅
    └── test_engine.py            ✅ 20+ unit test per tutte le funzioni di engine.py
```

**Legenda:** ✅ = fatto | ⬜ = da fare | 🔧 = fatto ma da rivedere

---

## 3. Architettura generale

```
Client (React)
    │
    ├── HTTP REST  →  /api/auth/*  /api/users/*  /api/games/*
    │
    └── WebSocket  →  /ws/{game_code}?token=<JWT>
                            │
                      game_handler.py
                            │
                 ┌──────────┴──────────┐
            engine.py             DB (SQLAlchemy)
          (pure functions)       (GameSession, GamePlayer, ...)
```

- **REST** gestisce: autenticazione, profilo utente, creazione/join lobby, leaderboard.
- **WebSocket** gestisce: tutto il gameplay in tempo reale (ogni messaggio è un JSON `{action: "...", ...}`).
- **engine.py** (core, ~165 righe): funzioni pure testabili (roll, combat, deck, death, ELO). Re-esporta tutto da `engine_boss`.
- **engine_boss.py** (~1000 righe): sistema boss completo — tutti i 100 boss, query helper, `apply_boss_ability`. Separato per leggibilità; nessuna modifica al callee.
- **engine_cards/** (package): effetti carte azione. Entry-point: `apply_action_card_effect(card, player, game, db, *, target_player_id)`. Un modulo per categoria: `economica` (1–8, 41–48, 81–88, 121–125, 159–168), `offensiva` (9–18, 49–54, 89–95, 126–130, 141–150), `difensiva` (19–25, 55–58, 96–100, 131–135, 151–158), `manipolazione` (26–30, 59–62, 101–105, 136, 169–171), `utilita` (31–37, 63–69, 80, 106–110, 137–138, 172–180), `interferenza` (38–40, 70–79, 111–120, 139–140, 181–190). Per aggiungere carte: definisci la funzione `_card_N` PRIMA del dict `MODULO: dict = {…}`, poi aggiungi `N: _card_N` al dict. `__init__.py` unisce tutti i dict e fa il dispatch per numero carta.
- **game_handler.py** (thin router, 65 righe): routing WS. Tutta la logica è in `handlers/` e `game_helpers.py`.
- **handlers/lobby.py**: join, select_character, start_game.
- **handlers/turn.py**: draw_card, play_card, buy_addon, use_addon, end_turn.
- **handlers/combat.py**: start_combat, roll_dice, retreat, declare_card, declare_card_type.
- **game_helpers.py**: helper condivisi (`_build_game_state`, `_error`, `_broadcast_state`, `_apply_elo`, `_send_hand_state`, …).
- **manager.py** tiene in memoria le connessioni WS attive raggruppate per `game_code`.

---

## 4. Database — Modelli

### `users`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| nickname | VARCHAR(50) UNIQUE | |
| password_hash | VARCHAR(255) | bcrypt |
| elo_rating | INT | default 1000 |
| games_played | INT | |
| games_won | INT | |
| created_at | DATETIME | server_default |

### `action_cards`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| number | INT UNIQUE | numero carta (1–300) |
| name | VARCHAR(100) UNIQUE | |
| card_type | VARCHAR(50) | Offensiva / Difensiva / Economica / Manipolazione dado / Interferenza / Utilità |
| when | VARCHAR(200) | quando giocarla |
| effect | TEXT | |
| rarity | ENUM | Comune / Non comune / Raro / Leggendario |
| copies | INT | copie nel mazzo: Comune=3, NC=2, Raro=1, Legg=1 |

### `boss_cards`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| number | INT UNIQUE | |
| name | VARCHAR(100) UNIQUE | |
| hp | INT | |
| dice_threshold | INT | es. 6 = "tira ≥ 6 per colpire" |
| ability | TEXT | |
| reward_licenze | INT | licenze al giocatore se sconfitto |
| has_certification | BOOL | se la vittoria dà una certificazione |
| difficulty | VARCHAR(20) | Facile / Media / Alta / Leggendaria |

### `addon_cards`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| number | INT UNIQUE | |
| name | VARCHAR(100) UNIQUE | |
| addon_type | ENUM | Passivo / Attivo |
| effect | TEXT | |
| synergy | TEXT | nullable |
| rarity | ENUM | Comune / Non comune / Raro / Leggendario |
| cost | INT | default 10 licenze |

### `game_sessions`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| code | VARCHAR(8) UNIQUE | codice invito |
| status | ENUM | waiting / in_progress / finished |
| max_players | INT | 2–4 |
| current_turn_index | INT | indice in `turn_order` |
| turn_number | INT | |
| current_phase | ENUM | draw / action / combat / end |
| action_deck_1 / action_deck_2 | JSON | due metà del mazzo azione (player sceglie da quale pescare) |
| action_discard | JSON | scarto condiviso — tutte le carte azione giocate; rimescolato e ridistribuito tra i due mazzi quando uno si esaurisce |
| boss_deck_1 / boss_deck_2 | JSON | due metà del mazzo boss |
| boss_market_1 / boss_market_2 | INT nullable | BossCard.id del boss visibile nel "mercato" |
| boss_graveyard | JSON | boss sconfitti senza certificazione (boss con cert rimossi permanentemente) |
| addon_deck_1 / addon_deck_2 | JSON | due metà del mazzo addon |
| addon_market_1 / addon_market_2 | INT nullable | AddonCard.id dell'addon visibile nel "mercato" |
| addon_graveyard | JSON | addon persi dai giocatori alla morte o distrutti da effetti carta |
| turn_order | JSON | lista di GamePlayer.id in ordine di turno |
| winner_id | FK → game_players | nullable |
| last_defeated_boss_id | INT nullable | ultimo boss sconfitto — usato da boss 55 (mimic) e boss 74 (shape shifter) |
| last_defeated_legendary_boss_id | INT nullable | ultimo boss leggendario (cert) sconfitto — usato da boss 100 (omega) |
| banned_card_ids | JSON | carte permanentemente bandite da boss 56 (Change Data Capture Lurker) |
| created_at / finished_at | DATETIME | |

### `game_players`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| game_id | FK → game_sessions | |
| user_id | FK → users | |
| seniority | ENUM | Junior / Experienced / Senior / Evangelist |
| role | VARCHAR(100) | ruolo Salesforce (es. "Platform Developer I") |
| hp / max_hp | INT | max_hp = f(seniority): J=1, E=2, S=3, Ev=4 |
| licenze | INT | default 3 |
| certificazioni | INT | default 0, vince a 5 — conteggio denormalizzato di `len(trophies)` |
| trophies | JSON | lista di BossCard.id guadagnati come trofei (boss con cert sconfitti). Visibili a tutti. Rubabili/distruggibili da carte azione avversarie. Se distrutto → `boss_graveyard`. |
| cards_played_this_turn | INT | max 2 per turno |
| is_in_combat | BOOL | |
| current_boss_id | FK → boss_cards | nullable |
| current_boss_hp | INT | HP attuale del boss in combattimento |
| current_boss_source | VARCHAR(10) | `market_1` / `market_2` / `deck_1` / `deck_2` — determina logica vittoria/sconfitta |
| combat_round | INT | round corrente di combattimento |
| combat_state | JSON nullable | stato transiente per-combat. Chiavi chiave: `resurrection_used`, `necromancer_resurrected`, `locked_addon_id`, `stolen_addon_id`, `petrified_card_ids`, `doomsayer_prediction_cap`, `loyalty_points`, `boss_ability_disabled_until_round`, `boss_threshold_reduction`, `double_damage_until_round`, `force_field_until_round`, `try_scope_until_round`, `entitlement_process_until_round`, `disaster_recovery_ready`, `on_error_continue_ready`, `fault_path_active`, `transform_element_active`, `pause_element_rounds_remaining`, `dynamic_content_reroll`, `chaos_mode_next_roll`, `einstein_sto_next_roll_bonus`, `next_roll_forced`, `critical_system_until_round`, `predictive_model_prediction`, `message_transformation_active`, `service_forecast_use_threshold`, `omni_channel_next_hit_bonus`, `queue_routing_double_damage_round`, `escalation_rule_active`, `contact_center_until_round`, `marketing_automation_turns_remaining`, `next_addon_price_half`, `addons_blocked_until_boss_defeat`, `campaign_influence_remaining`, `pardot_form_handler_remaining` — resettato a `{}` ad ogni nuovo combattimento (tranne flag cross-turn) |
| pending_addon_cost_penalty | INT | extra costo licenze sul prossimo acquisto addon (boss 26); resettato dopo il primo acquisto |
| score / bosses_defeated | INT | per ELO |

### `player_addons`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| player_id | FK → game_players | |
| addon_id | FK → addon_cards | |
| is_tapped | BOOL | tap/untap mechanic |

### `player_hand_cards`
| Campo | Tipo | Note |
|---|---|---|
| id | PK | |
| player_id | FK → game_players | |
| action_card_id | FK → action_cards | |

---

## 5. API REST

Base URL: `/api`

### Auth
| Metodo | Endpoint | Auth | Descrizione |
|---|---|---|---|
| POST | `/auth/register` | no | Registra nuovo utente |
| POST | `/auth/login` | no | Login, restituisce JWT |
| GET | `/auth/me` | Bearer | Profilo utente corrente |

### Users
| Metodo | Endpoint | Auth | Descrizione |
|---|---|---|---|
| GET | `/users/leaderboard?limit=20` | no | Top giocatori per ELO |
| GET | `/users/{nickname}` | no | Profilo pubblico utente |

### Games
| Metodo | Endpoint | Auth | Descrizione |
|---|---|---|---|
| GET | `/games` | no | Lista lobby aperte (waiting) |
| POST | `/games` | Bearer | Crea nuova partita, restituisce codice |
| GET | `/games/{code}` | no | Info lobby/partita |

---

## 6. WebSocket — Protocollo

**Connessione:** `ws://host/ws/{game_code}?token=<JWT>`

Tutti i messaggi sono JSON. Il server autentica via JWT al momento della connessione.

### Client → Server (azioni)

| `action` | Payload | Quando |
|---|---|---|
| `join_game` | — | Primo join o reconnect |
| `select_character` | `{seniority, role}` | In lobby |
| `start_game` | — | Host con ≥2 giocatori in lobby |
| `draw_card` | `{deck: 1\|2}` | Fase `draw`, proprio turno — sceglie da quale mazzo pescare |
| `play_card` | `{hand_card_id}` | Fase `action`, proprio turno |
| `buy_addon` | `{source: "market_1"\|"market_2"\|"deck_1"\|"deck_2"}` | Fase `action`, proprio turno |
| `use_addon` | `{player_addon_id}` | Fase `action`, proprio turno (addon Attivi) |
| `start_combat` | `{source: "market_1"\|"market_2"\|"deck_1"\|"deck_2"}` | Fase `action`, proprio turno |
| `roll_dice` | — | Fase `combat`, proprio turno |
| `retreat_combat` | — | Fase `combat`, proprio turno |
| `end_turn` | — | Fase `action` o `draw`, proprio turno |
| `declare_card` | `{hand_card_id}` | Fase `combat`, prima di `roll_dice` contro boss 33 — dichiara la carta che si intende giocare |
| `declare_card_type` | `{card_type: "Offensiva"\|"Difensiva"}` | Fase `combat`, dopo `start_combat` contro boss 86 — dichiara il tipo di carte che si potrà giocare |
| `play_reaction` | `{hand_card_id}` | Fuori dal proprio turno — risposta a `reaction_window_open`; gioca una carta interferenza |
| `pass_reaction` | — | Fuori dal proprio turno — rinuncia alla finestra di reazione |

### Server → Client (eventi)

| `type` | Payload principale | Trigger |
|---|---|---|
| `game_state` | snapshot completo incl. `boss_market_1/2`, `addon_market_1/2`, conteggi mazzi | join, reconnect, dopo ogni azione |
| `player_joined` | `{user_id, nickname}` | nuovo giocatore in lobby |
| `player_left` | `{user_id}` | disconnessione |
| `game_started` | — | partita avviata |
| `turn_started` | `{player_id}` | inizio turno |
| `card_drawn` | `{player_id}` | carta pescata |
| `card_played` | `{player_id, card}` | carta giocata |
| `addon_bought` | `{player_id, addon}` | addon acquistato |
| `addon_used` | `{player_id, addon_id}` | addon attivato |
| `combat_started` | `{player_id, boss}` | combattimento iniziato |
| `dice_rolled` | `{player_id, roll, result, boss_hp, player_hp}` | dado tirati |
| `combat_ended` | `{player_id, boss_defeated?, player_died?}` | fine combattimento |
| `player_died` | `{player_id, lost}` | penalità morte applicata |
| `turn_ended` | `{player_id, next_player_id}` | fine turno |
| `game_over` | `{winner_id}` | partita terminata |
| `hand_state` | `{hand: [...], addons: [...]}` | privato — inviato solo al giocatore dopo draw, play, morte, reconnect |
| `error` | `{message}` | errore di validazione/stato |
| `reaction_window_open` | `{trigger_card, attacker_player_id, timeout_ms}` | privato al target — si è aperta una finestra di reazione (8 s) |
| `reaction_window_closed` | — | privato al target — finestra chiusa (timeout o risposta ricevuta) |
| `reaction_resolved` | `{reactor_player_id, original_cancelled, reaction_effect}` | broadcast — come è stata risolta la reazione |

---

## 7. Game Engine

File: `app/game/engine.py`
**Funzioni pure** — nessuna dipendenza da DB o WebSocket. Testabili in isolamento.

| Funzione | Input | Output | Note |
|---|---|---|---|
| `roll_d10()` | — | int 1–10 | |
| `resolve_combat_round(dice, threshold)` | int, int | `"hit"` / `"miss"` | hit se dice ≥ threshold |
| `calculate_max_hp(seniority)` | Seniority | int | J=1, E=2, S=3, Ev=4 |
| `check_victory(certificazioni)` | int | bool | True se ≥ 5 |
| `shuffle_deck(deck)` | list | list | copia + shuffle |
| `split_deck(deck)` | list | (list, list) | divide un mazzo shufflato in due metà bilanciate |
| `build_action_deck(card_ids_by_rarity)` | dict | list | Comune×3, NC×2, Raro×1, Legg×1 |
| `draw_cards(deck, discard, count)` | list, list, int | (drawn, deck, discard) | reshuffle automatico |
| `apply_death_penalty(hand, licenze, addons)` | list, int, list | dict | perde 1 carta random, 1 licenza, 1 addon |
| `expected_score(rating_a, rating_b)` | int, int | float | formula ELO standard |
| `update_elo(ratings, winner_index)` | list[int], int | list[int] | ELO multiplayer, floor a 100 |
| `boss_roll_mode(boss_id, combat_round)` | int, int | `str \| None` | Override del tiro dado: `"worst_of_2"` o None. combat_round 1-indexed. |
| `boss_addons_disabled(boss_id, combat_round)` | int, int | bool | True se gli addon del giocatore sono bloccati questo round. |
| `boss_offensive_cards_blocked(boss_id)` | int | bool | True se le carte offensive sono vietate durante questo combattimento. |
| `boss_interference_doubled(boss_id)` | int | bool | True se l'interferenza degli avversari ha efficacia doppia. |
| `boss_threshold(boss_id, base_threshold, current_hp)` | int, int, int | int | Soglia dado effettiva (può cambiare per fasi o condizioni). |
| `apply_boss_ability(boss_id, trigger, *, dice_result, combat_round)` | int, str, ... | dict | Effetti collaterali del boss per il trigger dato. Chiavi: `extra_damage`, `boss_heal`, `discard_cards`, `steal_licenze`, `opponent_gains_licenza`. |

### Costanti

```python
CERTIFICATIONS_TO_WIN = 5
STARTING_LICENZE = 3
STARTING_HAND_SIZE = 4
MAX_HAND_SIZE = 10
MAX_CARDS_PER_TURN = 2
ADDON_BASE_COST = 10
```

---

## 8. Flusso di gioco

```
LOBBY
  └─ giocatori fanno join_game + select_character
  └─ host invia start_game

PARTITA (ciclo per ogni giocatore)
  1. DRAW PHASE
     └─ draw_card  → pescata una carta, fase passa ad ACTION

  2. ACTION PHASE  (può ripetere finché vuole)
     ├─ play_card       (max 2 per turno)
     ├─ buy_addon       (costa licenze)
     ├─ use_addon       (addon Attivi tappati)
     ├─ start_combat    → passa a COMBAT
     └─ end_turn        → turno successivo

  3. COMBAT PHASE  (una volta per turno)
     └─ roll_dice (ripetuto)
         ├─ HIT:  boss_hp -= 1
         │    └─ boss_hp = 0 → BOSS SCONFITTO
         │         ├─ reward licenze + eventuale certificazione
         │         ├─ check_victory → se 5 cert. → GAME OVER
         │         └─ torna ad ACTION PHASE
         └─ MISS: player_hp -= 1
              └─ player_hp = 0 → MORTE
                    ├─ penalità: -1 carta, -1 licenza, -1 addon
                    ├─ respawn a max_hp
                    ├─ boss torna in cima al mazzo
                    └─ torna ad ACTION PHASE
     └─ retreat_combat → torna ad ACTION (boss in cima al mazzo)

FASE FINALE (end_turn)
  ├─ step 1: abilità "fine turno" (TODO: trigger_passive_addons on_turn_end)
  ├─ step 2: scarto eccesso carte (hand > 10, auto-discard last drawn)
  ├─ step 3: effetti "until end of turn" scadono (TODO)
  ├─ step 4: reset HP a max_hp
  ├─ cleanup Card 18 (addon block) e Card 37 (free trial addon)
  ├─ reset cards_played_this_turn = 0
  └─ indice avanza al prossimo giocatore → fase torna a DRAW

INIZIO TURNO SUCCESSIVO (draw_card = FASE INIZIALE)
  ├─ step 1: untap tutti gli addon del giocatore attivo
  ├─ step 2: abilità "inizio turno" (TODO: trigger_passive_addons on_turn_start)
  └─ step 3: pesca 1 carta → fase passa ad ACTION

MORTE DEL BOSS (GDD §5.6 — 7 step)
  ├─ step 1: abilità pre-ricompensa (revive boss 25, re-insert boss 34)
  ├─ step 2: award Licenze reward
  ├─ step 3: award Certificazione (se boss-cert)
  ├─ step 4: abilità post-ricompensa (bonus cert/licenze, unlock addon, ecc.)
  ├─ step 5: Trofeo (boss-cert → player.trophies) o Cimitero Boss (non-cert)
  ├─ step 6: boss_graveyard aggiornato
  └─ step 7: mercato rifornito

MORTE DEL GIOCATORE
  ├─ penalità: -1 carta, -1 licenza, -1 addon
  ├─ tutti gli AddOn rimanenti vengono tappati (GDD §6)
  ├─ respawn a max_hp
  ├─ boss torna in cima al mazzo
  └─ torna ad ACTION PHASE
```

---

## 9. Stato di avanzamento

### ✅ Completato

- [x] Modelli DB: `User`, `ActionCard`, `BossCard`, `AddonCard`, `GameSession`, `GamePlayer`, `PlayerAddon`, `PlayerHandCard`
- [x] Config e database setup (SQLAlchemy 2.0 + pydantic-settings)
- [x] Auth: registro, login, JWT, `get_current_user`
- [x] API REST: auth, users (leaderboard), games (lista lobby, crea, info)
- [x] WebSocket: `ConnectionManager` (rooms per game_code)
- [x] WebSocket: `events.py` — `ClientAction` e `ServerEvent` come classi
- [x] WebSocket: `game_handler.py` — routing completo incluso `use_addon` e ELO end-game
- [x] Game Engine: tutte le funzioni pure (roll, combat, death, deck, victory, ELO)
- [x] `main.py`: FastAPI app, CORS, router REST, endpoint WebSocket con auth JWT
- [x] Alembic: struttura configurata (`env.py`, `script.py.mako`, `alembic.ini`)
- [x] `app/models/__init__.py` — importa tutti i modelli (Alembic autogenerate pronto)
- [x] `scripts/seed_cards.py` — parser .md → insert DB, idempotente
- [x] `tests/test_engine.py` — 20+ unit test per tutte le funzioni di engine.py
- [x] `backend/Dockerfile` — image Python 3.12-slim
- [x] `docker-compose.yml` — servizi `postgres:16-alpine` + `backend`, volume cards montato in `/cards`
- [x] `backend/entrypoint.sh` — attende Postgres, esegue `alembic upgrade head`, seed carte, avvia uvicorn
- [x] `scripts/seed_cards.py` — gestisce path Docker (`/cards`) e path locale automaticamente
- [x] **Reconnect mano privata** — `join_game` durante partita `in_progress` ora invia `game_state` a tutti + evento privato `hand_state` solo al giocatore che si riconnette. `hand_state` inviato anche dopo `start_game`, `draw_card`, `play_card` e penalty di morte.
- [x] **Doppi mazzi + mercato** — `start_game` divide tutti i mazzi in due metà; boss e addon hanno 1 carta visibile per mazzo nel "mercato". `draw_card` accetta `{deck: 1|2}`. `start_combat` e `buy_addon` accettano `{source: market_1|market_2|deck_1|deck_2}`. Logica vittoria/sconfitta rispetta le regole del mercato. Migration `0002_dual_decks.py`.
- [x] **3 mazzi degli scarti condivisi** — `action_discard` (scarto azione, rimescolato tra i 2 mazzi quando si esauriscono), `boss_graveyard` (boss senza cert), `addon_graveyard` (addon persi/distrutti). Migration `0003_shared_discards.py`.
- [x] **Trofei boss con certificazione** — boss cert sconfitti diventano trofei fisici del giocatore (`player.trophies`). Possono essere rubati (→ trofei avversario) o distrutti (→ `boss_graveyard`). Visibili a tutti nel `game_state`. Migration `0004_player_trophies.py`.
- [x] **Boss ability system (boss 1–100, COMPLETO)** — architettura a due livelli in `engine.py` + wiring completo in `game_handler.py`. Tutti i trigger (on_combat_start / on_round_start / after_miss / after_hit / on_player_damage / on_round_end / on_boss_defeated) cablati. Tutti i query helper applicati nei punti giusti del flusso.
- [x] **Migration `0005_combat_state.py`** — aggiunge `GamePlayer.combat_state` (JSON), `GamePlayer.pending_addon_cost_penalty` (INT), `GameSession.last_defeated_boss_id` (INT), `GameSession.last_defeated_legendary_boss_id` (INT), `GameSession.banned_card_ids` (JSON).
- [x] **Wiring boss residui (25, 26, 31, 34, 55, 56, 74, 82, 84, 91, 94, 100)** — sfruttano i nuovi DB fields. One-shot revive (25), one-shot necromancer (34), addon cost penalty (26), lock/unlock addon (31), steal/return addon (91), petrify cards (82), doomsayer prediction cap (84), loyalty shield (94), mimic routing (55), shape-shifter routing (74), omega routing (100), permanent card ban (56).
- [x] **Refactoring moduli** — `engine.py` (1154 righe) → `engine.py` (core, 165 righe) + `engine_boss.py` (boss system, 1001 righe). `game_handler.py` (1887 righe) → thin router (65 righe) + `game_helpers.py` (156 righe) + `handlers/lobby.py` (151 righe) + `handlers/turn.py` (480 righe) + `handlers/combat.py` (1079 righe). Nessuna logica modificata. Backward-compatible tramite `from app.game.engine_boss import *` in engine.py.
- [x] **Sistema reazione out-of-turn** — `reaction_manager.py`: asyncio Event per finestre di reazione (8 s timeout, in-memory, no DB). `_handle_play_card` apre una finestra se la carta colpisce un avversario con budget carte disponibile. Il target può rispondere con `play_reaction {hand_card_id}` o `pass_reaction`. Risoluzione: Shield Platform (carta 20) annulla l'originale; Chargeback (carta 7) su furto Licenze annulla + dà +1L; altre interferenze si applicano entrambe. Budget carte condiviso in-turn/out-of-turn: `cards_played_this_turn` conta entrambi. Nuovi ClientAction: `play_reaction`, `pass_reaction`. Nuovi ServerEvent: `reaction_window_open` (privato), `reaction_window_closed` (privato), `reaction_resolved` (broadcast).
- [x] **Lucky Roll (carta 27) — redesign come reazione post-roll**
  - `_handle_play_card`: guard aggiunto prima del consumo — carta 27 non è consumabile via `play_card` (errore restituito al client).
  - `_handle_roll_dice`: dopo roll + modificatori (Optimizer 26, Chaos 29), se il player ha carta 27 in mano e ha budget carte, apre finestra di reazione privata (`reaction_window_open` con `reason: "lucky_roll"`, `pending_roll`, `pending_result`, `threshold`, timeout 8 s). Se il player risponde con `play_reaction`, la carta viene consumata (`cards_played_this_turn++`) e il dado viene ritirto (il nuovo risultato sostituisce il precedente). Broadcast `lucky_roll_used` con `new_roll`. Card 26 (forced roll) ha priorità: se attiva, la finestra non si apre.
  - `engine_cards/manipolazione.py`: `_card_27` è ora no-op (reaction-only).
  - `events.py`: aggiunto `LUCKY_ROLL_USED = "lucky_roll_used"`.

- [x] **Allineamento GDD §4 + §5.6 + §6 — struttura turno a tre fasi e morte boss/giocatore**
  - `_handle_draw_card`: untap addons + TODO on_turn_start spostati qui (prima erano in end_turn) → implementa correttamente FASE INIZIALE (step 1 untap, step 2 abilità inizio turno, step 3 pesca).
  - `_handle_end_turn`: aggiunta FASE FINALE — step 2 scarto eccesso carte (hand > 10, auto-discard), step 3 TODO effects expire, step 4 HP reset a max_hp.
  - `_handle_play_card` + `_handle_use_addon`: guard aggiornato da `!= TurnPhase.action` a `not in (action, combat)` → carte e addon usabili durante il combattimento.
  - `_handle_roll_dice` boss defeat: ordine riallineato a GDD §5.6 — step 1 (pre-reward: revive boss 25, re-insert boss 34 — ora questi ritornano SENZA aver già dato le ricompense), step 2 licenze, step 3 cert, step 4 post-reward, step 5–6 trofeo/cimitero, step 7 mercato.
  - `_handle_roll_dice` player death: aggiunto tap di tutti gli AddOn rimanenti (GDD §6).

- [x] **Effetti carte azione — carte 1–120 implementate** — Package `engine_cards/` con 6 moduli: `economica` (1–8, 41–48, 81–88), `offensiva` (9–18, 49–54, 89–95), `difensiva` (19–25, 55–58, 96–100), `manipolazione` (26–30, 59–62, 101–105), `utilita` (31–37, 63–69, 80, 106–110), `interferenza` (38–40, 70–79, 111–120). Keys batch 2 (41–60): `fought_this_turn`, `drip_program_remaining`, `object_store_licenze`, `next_addon_price_fixed`, `next_addon_price_discount`, `ampscript_reflected_until_round`, `try_scope_until_round`, `on_error_continue_ready`, `api_proxy_active` (TODO pieno), `entitlement_process_until_round`, `dynamic_content_reroll`, `einstein_sto_next_roll_bonus`. Keys batch 3 (61–80): `predictive_model_prediction` (61, card 26 next_roll_forced=7 per 62), `suppressed_draw` (70), `forced_queue_card_id` (71), `forced_reroll_next` (72), `routing_assigned` + `routing_assigned_boss_id` (74, TODO enforcement), `milestone_action_remaining` (76). Hooks combat.py: forced_reroll_next (pre-forced_roll) → predictive_model_prediction (read+consume before resolve) → predictive_bonus in _hit_damage → milestone_action after round (post death check). Hooks turn.py draw_card: suppressed_draw (skip draw + early return) + forced_queue_card_id (give queued card). Card 78 guard (reaction-only) in _handle_play_card. Keys batch 5 (101–120): `message_transformation_active` (105, auto-upgrade roll ≤3 to 6), `transform_element_active` (103, next miss → -1L instead of -1HP), `bounce_management_active` (113, reflect next Offensiva at attacker -2L), `jms_delay_active` (117, block next card targeting player), `api_rate_limit_max_cards` (116, cap card plays to 1, cleared in end_turn), `visitor_activity_turns` (112, declaration signal, decremented in end_turn), `event_monitoring_target_id` + `event_monitoring_remaining` (120, hook in play_card awards 1L/card), `tracking_pixel_target_id` + `tracking_pixel_turns` (111, TODO hook in broadcast), `spike_control_turns_remaining` (118, TODO cap in turn.py), `connect_channel` simplified to +2L (119). Cards 101/104 reuse `next_roll_forced`; card 102 reuses `boss_ability_disabled_until_round`. Keys batch 4 (81–100): `renewal_protected` (84, spares first addon from death-tap), `review_app_active` (96, threshold -2 round 1), `fault_path_active` (97, miss → +1L instead of HP damage), `pause_element_rounds_remaining` (98, round_nullified override), `web_to_case_active` (99, block next Offensiva targeting player), `preference_immunity_type` (100, block card type targeting player), `heroku_ci_active` (95, next hit kills boss if HP ≤ 2), `combat_boss_hits_received` (92, incremented on player damage in miss branch), `guided_selling_threshold_reduction` reuses consulting_hours keys (91), stacks boss_threshold_reduction (89). Hooks buy_addon: total_addon_licenze_spent += cost (card 87). Hooks turn.py play_card: immunity checks (99, 100) block original_cancelled before apply_action_card_effect.
- [x] **Boss 33, 45, 63, 83, 86 — TUTTI I 100 BOSS COMPLETAMENTE CABLATI**
  - Boss 33 (Experience Cloud Illusion): nuova action `declare_card` — il player dichiara la carta prima del tiro. Se miss, la carta viene consumata. Handler: `_handle_declare_card` + guard in `_handle_roll_dice`.
  - Boss 45 (Agentforce Rebellion): ogni round hijack di 1 addon random untapped (tappato); broadcast `addon_hijacked_by_boss`. Effetto invertito deferred a `apply_addon_effect`.
  - Boss 63 (Loyalty Management Trickster): auto-accept deal — +1 Licenza, soglia dado +1 per quel round (via `threshold_bonus` locale). Broadcast `boss_deal_auto_accepted`.
  - Boss 83 (Account Engagement Siren): auto-reject — broadcast `boss_siren_deal_rejected`, nessun effetto.
  - Boss 86 (Record Type Ravager): nuova action `declare_card_type` — player dichiara "Offensiva" o "Difensiva" a inizio combat. Server invia `card_type_declaration_required`. Scelta salvata in `combat_state.allowed_card_type`. Guard in `_handle_play_card` blocca carte del tipo sbagliato.
  - Nuovi ClientAction: `declare_card`, `declare_card_type`.
  - Nuovi ServerEvent di controllo: `card_declared_before_roll`, `card_type_declaration_required`, `card_type_declared`, `addon_hijacked_by_boss`, `boss_deal_auto_accepted`, `boss_siren_deal_rejected`.

### ⬜ Da fare

- [ ] **Effetti carte azione (carte 141–300)** — 140/300 implementate. Pattern: aggiungere funzione + chiave al dict del modulo della categoria (secondary dict pattern per carte oltre la 120). Vedere `cards/action_cards.md` batch 4+ (141–300).
  - **Validazione timing** — ogni carta ha un campo `Quando` che va verificato prima di giocarla (es. "durante combattimento", "fuori dal combattimento"). Da implementare in `can_play_card(card, game)` e chiamare in `_handle_play_card`.
  - **Knowledge Article (32)** — il riordino delle top 3 carte richiede un messaggio client follow-up con l'ordine preferito (non ancora implementato; attualmente solo preview).

- [ ] **Effetti addon (200 addon)** — `_handle_use_addon` tappa l'addon ma NON applica nessun effetto. Va creata `apply_addon_effect(addon, player, game, db)` per gli addon Attivi (uso manuale) e hook `trigger_passive_addons(event, player, game, db)` nei seguenti punti del flusso:
  - `on_draw` — in `_handle_draw_card` dopo aver pescato
  - `on_turn_end` — in `_handle_end_turn` prima di untappare gli addon
  - `on_addon_bought` — in `_handle_buy_addon` dopo l'acquisto
  - `on_roll` — in `_handle_roll_dice` prima/dopo il tiro dado
  Vedere `cards/addon_cards.md` per l'effetto completo di ogni addon.

- [x] **Abilità speciali boss (91–100)** — TUTTI I 100 BOSS IMPLEMENTATI in `engine.py`.
  - Nuovi campi effetto aggiunti per boss 91–100: `steal_and_use_addon`, `draw_bonus_cards`, `subscription_drain`, `permanently_destroy_addon`, `shuffle_all_hands`, `bonus_licenze_to_helpers`, `instant_win`.
  - Nuovi query helper: `boss_draw_costs_hp()` (92 — ogni pesca costa N HP), `boss_loyalty_shield()` (94 — N punti fedeltà → immune dado; ogni carta difensiva decrementa), `boss_redirects_damage_to_opponent()` (95 — danno rediretto a avversario random), `boss_compliance_penalty_per_extra_card()` (96 — extra HP per carta oltre la prima), `boss_is_omega()` (100 — route trigger al boss leggendario più recente sconfitto).
  - Handler da aggiornare: `steal_and_use_addon` (pesca addon random, applica effetto vs player, salva `stolen_addon_id`; restituito su defeat via `unlock_locked_addon`), `draw_bonus_cards` (pesca N extra a inizio combat; ognuna triggera `boss_draw_costs_hp`), `subscription_drain` (se licenze > 0 → -N; altrimenti -2N HP), `permanently_destroy_addon` (addon → `addon_graveyard`, non recuperabile), `shuffle_all_hands` (pool tutte le mani, shuffle, ridistribuisce), `bonus_licenze_to_helpers` (su defeat: ogni player con `cards_played_this_combat > 0` guadagna N licenze), `instant_win` (su defeat: skip check cert → vittoria immediata), `boss_loyalty_shield` (init `combat_state.loyalty_points`; mentre > 0 → skip dado danno; ogni carta difensiva decrementa), `boss_redirects_damage_to_opponent` (in `_handle_roll_dice` dopo_miss: deal HP a opponent random invece che al combattente), `boss_compliance_penalty_per_extra_card` (controlla in `_handle_play_card`: se `cards_played > 1` → deal (cards-1)×penalty HP), `boss_is_omega` (per ogni trigger: route anche a `game.last_defeated_legendary_boss_id` se non None).
  - Nuovi campi effetto aggiunti per boss 81–90: `petrify_cards`, `siren_deal`, `doomsayer_prediction_roll`, `force_card_type_declaration`, `aoe_unblockable_hp_damage`, `reveal_next_bosses`.
  - Nuovi query helper: `boss_jinx_on_draw()` (81 — handler tira d10 su ogni pesca; 1–3 scarta la carta), `boss_halves_card_effects()` (85 — tutti gli effetti carta dimezzati round down).
  - Aggiornati: `boss_immune_to_card_damage()` + case 89 (immune a carte round dispari), `boss_immune_to_dice()` + case 89 (immune a dado round pari), `boss_expires_after_rounds()` + case 90 (max 3 round).
  - Handler da aggiornare: `petrify_cards` (blocca N carte in hand per tutta la durata), `siren_deal` (evento WS accept/reject → +2 licenze, boss +1 HP, skip roll), `doomsayer_prediction_roll` (d10 → predizione durata; ogni round che supera il cap → extra_damage=1), `force_card_type_declaration` (evento WS → player sceglie Attack/Defense; filtra play_card per tipo), `aoe_unblockable_hp_damage` (come aoe_all_players_hp_damage ma bypassa carte difensive), `reveal_next_bosses` (legge top N da boss_deck, broadcast "boss_preview" a tutti), `boss_jinx_on_draw` (controlla in `_handle_draw_card` → d10 → 1–3 scarta carta appena pescata), `boss_halves_card_effects` (controlla in `_handle_play_card` → floor-divide tutti i valori numerici dell'effetto).
  - Nuovi campi effetto aggiunti per boss 71–80: `aoe_discard_all_hands`, `opponent_draws_card`, `reveal_all_licenze`, `refresh_hand`, `certification_exam_rolls`.
  - Nuovi query helper: `boss_heals_on_defensive_card()` (72), `boss_is_shape_shifter()` (74), `boss_immune_to_dice()` (78).
  - Aggiornati: `boss_addons_disabled()` + case 77, `boss_immune_to_card_damage()` + `combat_round` param + case 78, `boss_disables_all_addons()` + `combat_round` param + case 79, `boss_interference_blocked()` + case 79.
  - Handler da aggiornare: `aoe_discard_all_hands` (scarta N carte da ogni giocatore), `opponent_draws_card` (avversario random pesca), `reveal_all_licenze` (broadcast + free card al più ricco), `refresh_hand` (scarta mano + pesca N), `certification_exam_rolls` (5 × d10 → HP/licenze), `boss_immune_to_dice` (skip boss HP decrement), `boss_is_shape_shifter` (ogni 2 round route trigger a boss casuale da defeated_boss_ids), `boss_heals_on_defensive_card` (check in _handle_play_card se carta difensiva).
  - Nuovi campi effetto aggiunti per boss 61–70: `exam_roll`, `deal_offer`, `bonus_hp_per_player_addon`, `boss_splits_on_heavy_hit`.
  - Nuovi query helper: `boss_forces_top_card_play()` (64), `boss_cancels_offensive_if_revealed()` (65), `boss_blocks_retreat()` (66), `boss_death_addon_penalty()` (66), `boss_nullifies_round_on_low_roll()` (67), `boss_requires_approval_roll()` (69).
  - Handler da aggiornare: `exam_roll` (d10 → ±HP pre-combat), `deal_offer` (evento WS accept/reject → licenza + threshold +1), `bonus_hp_per_player_addon` (boss.hp += len(player.addons) all'inizio), `boss_splits_on_heavy_hit` (spawn boss duplicate con 3 HP), `boss_blocks_retreat` (blocca qualsiasi carta retreat), `boss_death_addon_penalty` (affianca `boss_death_licenze_penalty`), `boss_nullifies_round_on_low_roll` (skip danno se roll ≤ 2), `boss_requires_approval_roll` (d10 extra per carta → ≤4 carta consumata senza effetto).
  - Nuovi campi effetto aggiunti per boss 41–50: `licenza_or_hp_drain`, `hijack_addon`, `force_extra_card_discard`.
  - Nuovi campi effetto aggiunti per boss 51–60: `entry_fee_licenze`, `corrupt_deck_cards`, `makes_prediction`, `invert_random_hand_card`.
  - Nuovi query helper: `boss_hand_visible_to_opponents()` (41), `boss_immune_to_card_damage()` (43), `boss_heals_on_addon_use()` (49), `boss_expires_after_rounds()` (48).
  - Nuovi query helper per 51–60: `boss_damage_absorption()` (52), `boss_is_mimic()` (55), `boss_permanently_bans_used_cards()` (56), `boss_death_licenze_to_top_cert()` (57), `boss_heals_on_interference()` (59), `boss_blocks_addon_purchase()` (60).
  - Handler da aggiornare: `licenza_or_hp_drain`, `hijack_addon`, `force_extra_card_discard`, `boss_expires_after_rounds`, `boss_heals_on_addon_use`, `entry_fee_licenze` (paga o prendi HP), `corrupt_deck_cards` (sentinelle con id=-54 nel deck), `makes_prediction` (random coin flip → doppio effetto se corretto), `invert_random_hand_card` (set `combat_inverted_cards`), `boss_damage_absorption` (counter `combat_hits_absorbed`), `boss_is_mimic` (re-route trigger a `game.last_defeated_boss_id`), `boss_permanently_bans_used_cards` (`game.banned_card_ids`), `boss_death_licenze_to_top_cert`, `boss_heals_on_interference`, `boss_blocks_addon_purchase` (check in `_handle_buy_addon`).
  - Nuovi campi effetto aggiunti per boss 21–30: `aoe_all_hp_damage`, `reveal_hand`, `boss_revive`, `next_addon_cost_penalty`, `absorb_cards`, `return_absorbed_cards`.
  - Nuovi campi effetto aggiunti per boss 31–40: `lock_addon`, `unlock_locked_addon`, `opponent_discards_from_hand`, `bonus_chaos_roll`, `boss_revive_to_deck`, `aoe_all_players_hp_damage`.
  - Nuovi query helper: `boss_card_declared_before_roll()` (boss 33), `boss_cancels_next_card()` (boss 38), `boss_roll_mode` → `"second_of_2"` (boss 39).
  - `apply_boss_ability` ora accetta `current_hp` per effetti basati sulla fase (boss 37).
  - Handler da aggiornare: `lock_addon` (flag `combat_locked_addon_id`), `bonus_chaos_roll` (dado extra d10 → penalità casuale), `boss_revive_to_deck` (flag `batch_necromancer_resurrected`), `boss_cancels_next_card` (flag `cancel_next_card_this_round`), `boss_card_declared_before_roll` (campo `declared_card_id` nel combat state).

- [x] **Carte azione 121–140 — Batch 6 (Marketing Cloud & MuleSoft cont., Service Cloud, Pardot)**
  - **Economica 121–125**: Lead Score (121, +1L/carta in mano max5), Marketing Automation (122, +1L per carta giocata per 2 turni), Product Catalog (123, +3L o +5L con ≥2 addon), Price Book (124, prossimo addon a metà prezzo, min5), Approval Process (125, +4L se ≥10L).
  - **Offensiva 126–130**: Case Assignment Rule (126, escape + reward_licenze immediate), Omni-Channel (127, prossimo hit +1HP al boss), Einstein Case Classification (128, threshold -2 per 3 round), Boss Dossier (129, reveal boss + -1HP immediato), Queue-Based Routing (130, round neutro ora + 2HP al round dopo).
  - **Difensiva 131–135**: SLA Policy (131, entitlement_process 3 round), Escalation Rule (132, danno ≥2HP assorbe metà), Contact Center Integration (133, su HP perso pesca 1 carta per 2 round), Macro Builder (134, +1 al dado), Omni Supervisor (135, boss ability disabilitata 2 round).
  - **Manipolazione 136**: Service Forecast (136, usa soglia come risultato dado garantito).
  - **Utilità 137–138**: CPQ Rules Engine (137, guarda top 5 tieni 1 altri rimangono in ordine), Pardot Form Handler (138, mirror draw quando avversario pesca, max 2).
  - **Interferenza 139–140**: Prospect Lifecycle (139, target non può acquistare addon fino alla prossima sconfitta boss), Campaign Influence (140, per ogni Licenza guadagnata da chiunque +1L, max 3).
  - **Pattern secondary dict**: ECONOMICA_121, OFFENSIVA_126, DIFENSIVA_131, MANIPOLAZIONE_136, UTILITA_137, INTERFERENZA_139 — tutti esportati e importati da `__init__.py`.
  - **combat.py hooks aggiunti**: `service_forecast_use_threshold` (roll=threshold), `omni_channel_next_hit_bonus` (+1 _hit_damage), `queue_routing_double_damage_round` (2HP in miss branch), `escalation_rule_active` (assorbe metà su ≥2HP), `contact_center_until_round` (draw 1 carta su HP loss), `addons_blocked_until_boss_defeat` (clear su boss defeat).
  - **turn.py hooks aggiunti**: `marketing_automation_turns_remaining` (+1L in play_card; decrement in end_turn), `next_addon_price_half` (halve cost in buy_addon), `addons_blocked_until_boss_defeat` (block in buy_addon), `pardot_form_handler_remaining` (mirror draw in draw_card).

- [x] **Carte azione 141–190 — Batch 7 (Industries, Agentforce, Flows, AI, Interferenze avanzate)**
  - **Offensiva 141–150**: Manufacturing Cloud (141, 1HP/addon passivo max4), Automotive Cloud (142, best-of-2 roll per 2 round), Industries Cloud (143, 1HP/Certificazione), Appointment Bundle (144, 1HP/carta giocata questo turno), Service Territory (145, 1HP; 2HP se boss_graveyard>0), Digital HQ (146, 1HP/tipo carta distinto giocato max4), Agentforce Action (147, 2HP; 3HP se addon Leggendario), Loop Element (148, 1HP/hit precedente max3), Activation Target (149, disabilita boss ability permanentemente), Orchestration Flow (150, Leggendario — untap tutti gli addon).
  - **Difensiva 151–158**: Hyperforce Migration (151, disabilita threshold bonus e boss ability per N round), Net Zero Commitment (152, +1L per HP perso in combattimento), Environment Branch (153, assorbe il prossimo danno HP una volta), Sustainability Cloud (154, sconto addon pari a HP persi), Public Sector Solutions (155, immune a danno HP da carte per 1 turno), Travel Time Calc (156, se roll==soglia-1 skip danno), Resource Leveling (157, trasferisci 2L dal giocatore più ricco al più povero), Runtime Manager (158, sopravvivi con 1HP alla morte — flag cross-turno).
  - **Economica 159–168**: Service Report (159, +1L/boss sconfitto max7), Storefront Reference (160, +2L +1L per giocatore che ha comprato addon questo turno), Promotions Engine (161, -2L costo addon per 2 turni), Coupon Code (162, +3L), Inventory Availability (163, +1L per tipo addon assente nei mazzi), Revenue Dashboard (164, +1L/turno trascorso max6), Deal Insights (165, +hp×2 L), Financial Services Cloud (166, +1L per 10L possedute max3), Nonprofit Cloud (167, dona 2L a target; +3L e pesca 1), Consumer Goods Cloud (168, +1L per giocatore in partita).
  - **Manipolazione 169–171**: Model Builder (169, dopo 3 miss consecutivi next roll=10), RAG Pipeline (170, 1HP al boss + guarda top card boss/azione), Copilot Studio (171, roll+1 e tutti i valori +1 per il round).
  - **Utilità 172–180**: Tableau Dashboard (172, pesca 2 + guarda top2 boss deck), CRM Analytics (173, riordina top4 deck), App Analytics (174, recupera 1 carta dallo scarto), Profile Explorer (175, snapshot pubblico tutti i giocatori), Customer 360 (176, snapshot completo inclusa mano), Database Connector (177, recupera 1 carta dagli ultimi 10 scarti), VM Queue (178, code 3 carte fuori mano, si giocano 1/turno), API Autodiscovery (179, rivela next2 boss senza pescarli), Related Attribute (180, lega 2 addon +1 effetto quando uno si attiva).
  - **Interferenza 181–190**: Communications Cloud (181, forza target a giocare una carta specifica), Interaction Studio (182, disabilita boss ability del prossimo combattimento del target), Code Review (183, blocca 1 carta nella mano del target per 1 turno), Amendment Quote (184, -1 effetto addon target per 1 turno), Record Triggered Flow (185, +1L ogni volta che il target usa un addon, max3), Push Notification (186, forza target a giocare 1 carta immediatamente), API Manager (187, rate limit 1 azione/turno per 2 turni), Update Records (188, -1L al target per ogni pesca per 2 turni), Delete Records (189, rimuove 1 addon del target e lo blocca dal riacquisto per 3 turni), Unification Rule (190, tutti devono giocare solo un tipo di carta per 1 turno).
  - **combat.py hooks aggiunti (batch 7)**: `best_of_2_until_round` (max di 2 roll), `copilot_studio_boost_active` (roll+1), `_hyperforce_active` (sopprime scope_creep e boss ability in miss branch), `combat_hits_dealt` (incremento in hit branch), `model_builder_active`+`consecutive_misses` (traccia miss consecutive → next_roll_forced=10 dopo 3), `environment_branch_active` (skip HP damage una volta), `travel_time_calc_active` (roll==soglia-1 → skip danno), `net_zero_commitment_active` (+1L per HP perso), `sustainability_hp_lost` (contatore), `runtime_manager_ready` (sopravvivi con 1HP), `next_boss_ability_disabled` (persiste in `_persist_cs`, neutralizza start_effect).
  - **turn.py hooks aggiunti (batch 7)**: `update_records_licenze_drain_turns` (draw_card: -1L), `vm_queue_card_ids` (draw_card: consegna prima carta in coda), `code_review_blocked_card_ids` (play_card: blocca carta), `unification_rule_active`+`unification_rule_card_type` (play_card: solo il tipo mandato), `card_types_played_this_turn` (play_card: aggiorna lista tipi), `record_triggered_flow_remaining` (use_addon: +1L ai watcher), `deleted_addon_blocked_ids` (buy_addon: blocca riacquisto), `promotions_engine_turns_remaining` (buy_addon: -2L costo), `sustainability_discount_pending`+`sustainability_hp_lost` (buy_addon: sconto pari a HP persi), `bought_addon_this_turn` (buy_addon: flag per Storefront Reference). End_turn: pulizia di tutti i nuovi flag con decrement/clear appropriato.
  - **Pattern**: dict unico per modulo (no secondary dict); tutte le funzioni definite prima del dict `MODULO: dict = {...}`.

- [x] **Carte azione 191–210 — Batch 8 (Flow, Records, Difensiva avanzata, Economica)**
  - **Offensiva 191–195**: Autolaunched Flow (191, auto -1HP boss quando HP<2), Screen Flow (192, usa 7 se roll<7 per 1 round), Decision Element (193, target -1HP → player +2L), Assignment Element (194, redistribuisce L: player prende metà superiore), Subflow (195, +1L o -1HP boss in base all'ultima carta giocata).
  - **Utilità 196–200**: Get Records (196, pesca 1 carta + peek top2 boss deck), Create Records (197, recupera 1 carta dallo scarto o +1L), Einstein Recommendation (198, primo addon del mercato gratis o +2L fallback), Segment Builder (199, scegli deck da cui pescare per 2 turni), Publication List (200, gruppo beneficiario pesca 1, altri scartano 1).
  - **Difensiva 201–207**: Web Studio (201, carte offensive avversarie -1 danno per turno), Prospect Grade (202, +L in base alla classifica: 1°=5 2°=3 3°=2 4°+=1), Sender Profile (203, soglia dado -2 per 1 round), Delivery Profile (204, blocca danno HP del prossimo round miss), MicroSite (205, +1L per ogni turno senza danno, max 4), Landing Page (206, prossima offensiva vs player → +2L invece di danno), Feedback Management (207, +1L per ogni carta giocata contro di te, max 3).
  - **Economica 208–210**: Smart Capture Form (208, +1L per giocatore con hand_revealed_this_turn), Activity Score (209, +4L se consecutive_turns_with_cards >= 3), Activity Timeline (210, recupera 1 carta da scarto + +1L).
  - **combat.py hooks**: `screen_flow_active` (roll ≥ 7 forzato), `sender_profile_threshold_reduction` (threshold -2 consume), `delivery_profile_block_active` (skip HP damage in miss, prima di environment_branch), `autolaunched_flow_ready` (auto -1HP boss se player.hp < 2 post-danno).
  - **turn.py hooks**: `landing_page_active` (cancella Offensiva → +2L al target), `feedback_management_remaining` (any card vs target → +1L, decrement), `web_studio_active` (+1L refund al target su Offensiva), `consecutive_turns_with_cards` (increment in end_turn se cards_played>0, else reset), `turns_not_attacked` (increment se hp==max_hp in end_turn, else reset), `hand_revealed_this_turn` (clear in end_turn).

- [x] **Carte azione 211–230 — Batch 9 (Sales Cloud, Einstein AI, Slack, MuleSoft)**
  - **Economica 211–214, 230**: Sales Engagement (211, ogni carta avversaria giocata contro di te → +1L), High Velocity Sales (212, fuori: +3L; in combat: boss -2HP ma no altre azioni), Cadence (213, +2L per ogni 2 turni senza combattere), Customer Lifecycle (214, +1L/fase da 5 turni max5), Client Application (230, +2L o +4L se avversario ha più addon).
  - **Manipolazione 216–220**: Einstein Vision (216, soglia dado -1 permanente), Einstein Language (217, recupera scarto + next roll +1), Einstein Sentiment (218, boss ability disabilitata round successivo), Vector Database (219, recupera scarto + next roll +1), Grounding Data (220, soglia non modificabile per 2 turni).
  - **Utilità 215, 221, 223, 226–227**: B2B Analytics (215, snapshot completo avversario per 1 turno), Workflow Step (221, prossima carta pescata si gioca gratis), App Home (223, +1L passivo ogni draw phase per tutta la partita), Shortcut (226, +2 slot carte questo turno), Anypoint Visualizer (227, grafo completo visibile 1 turno).
  - **Interferenza 222, 224–225, 229**: Block Kit (222, riduce prossima carta avversario di 1 punto effetto), Canvas (224, boss semplificato 1HP+no ability), Huddle (225, tutti rivelano la mano), SLA Tier (229, tappa 1 addon del target).
  - **Offensiva 228**: Runtime Fabric (228, boss -1HP; se HP>2 → -2HP).
  - **combat.py hooks**: `grounding_data_until_turn` (sopprime scope_creep e consulting_hours se attivo).
  - **turn.py hooks**: `high_velocity_all_in` (blocca ulteriori carte in play_card), `shortcut_extra_plays` (aumenta max_cards per il turno), `app_home_passive` (draw phase: +1L all'inizio), `sales_engagement_active` (ogni carta vs target → +1L a target), `block_kit_pending` (riduce 1L guadagnata dalla prossima carta del player). End_turn: cleanup di tutti i nuovi flag; `cadence_no_combat_turns` incrementato/resettato.

- [x] **Carte azione 231–250 — Batch 10 (MuleSoft, Agentforce, DevOps)**
  - **Offensiva 231, 233, 240**: Mule Event (231, -1HP boss + draw 1), Mule Flow (233, -1HP/carta in mano max3), Batch Scope (240, DOT -1HP/round per 3 round).
  - **Economica 235, 241, 244**: Anypoint Exchange (235, +2L + scambia 1 carta mano↔mazzo), Object Storage (241, archivia fino a 3L sicure; restituite al turno successivo), Prompt Template (244, +2L per addon Passivo max5).
  - **Utilità 232, 234, 238–239, 242–243, 245, 247–250**: Mule Message (232, rivela mano + draw), Integration Pattern (234, +1 alla 2a carta del turno), Recipe (238, consuma 1 Economica in mano + +3L), SFTP Connector (239, archivia fino a 2 carte; restituite al prossimo turno), App Builder (242, 2 carte stesso tipo → draw bonus), Einstein GPT (243, recupera scarto + free play), Agent Skill (245, +2L proxy passivo), Agent Action Plan (247, guarda 3 + keep/requeue/discard), Pipeline Promotion (248, sposta top boss in fondo), Work Item (249, recupera 1 carta a fine turno), Pipeline Stage (250, scarto → top deck).
  - **Interferenza 236, 237, 246**: API Governance (236, tutti devono dichiarare le carte per 1 turno), Dataflow (237, ruba 1 carta dalla mano del target), Agent Topic (246, come Unification Rule con tipo "Economica").
  - **combat.py hooks**: `batch_scope_dot_rounds` (DOT -1HP boss ogni round, decrement/clear).
  - **turn.py hooks**: `einstein_gpt_free_play` (skip cards_played_this_turn increment per 1 carta), `integration_pattern_boost` (+1L alla 2a carta giocata), `app_builder_active`+`app_builder_type_counts` (draw quando tipo raggiunge 2 play), `sftp_reserve_card_ids` (restituzione carte in draw_card), `work_item_active` (recupera 1 scarto in end_turn), `api_governance_active` (clear in end_turn).

- [x] **Carte azione 251–270 — Batch 11 (Salesforce Community, Difensiva, CTA, Utility avanzata)**
  - **Economica 251–257**: Trailblazer Community (251, +1L/giocatore certificato), AppExchange Partner (252, +2L o +5L con ≥5 addon), Dreamforce Badge (253, +3L+draw), MVP Award (254, +5L se ≥2 tipi diversi giocati), Platinum Partner (255, +3L/certificazione), Green IT (256, +3L; +5L se no Offensiva), Education Cloud (257, giocatore con meno boss pesca 1; se tu peschi 2).
  - **Difensiva 258–260**: Salesforce Tower (258, HP floor=1 per 1 turno), Nonprofit Success Pack (259, +2HP + +1HP al giocatore più debole), Admin Hero (260, +2HP+draw se Admin role; +1HP altrimenti).
  - **Offensiva 261–262**: CTA Board (261, boss con ≤3HP → sconfitto immediatamente), World Tour Event (262, +2L su ogni boss defeat per 1 turno; primo combattente +1L extra).
  - **Utilità 263–267, 269–270**: Architect Guild (263, Architecture players pescano 1; tu peschi 2), Trailhead Playground (264, pesca 3 tieni 1 altri tornano nel mazzo), Trailmix (265, prendi 1 per tipo dagli ultimi 9 scarti), Salesforce Ben (266, draw2 + peek boss deck), Buyer Relationship Map (267, snapshot addon di tutti), Trailhead GO (269, refund slot carta), Success Community (270, target ti dà 1 carta).
  - **Interferenza 268**: ISV Summit (tutti mostrano 1 addon; chi non ne ha -1L; player +1L per addon mostrato).
  - **combat.py hooks**: `salesforce_tower_active` (HP = max(1, hp-damage)), `world_tour_event_active`+`world_tour_event_first_bonus` (+2L/+1L su boss defeat).
  - **turn.py end_turn**: cleanup `salesforce_tower_active`, `world_tour_event_active`, `world_tour_event_first_bonus`.

- [x] **Carte azione 271–300 — Batch 12 (Ultime 30 carte: Ohana, ISV, Leggendarie, Utility finale)**
  - **Interferenza 271, 277, 278**: Ohana Pledge (271, tregua Ohana 2 turni su tutti gli avversari), Form Handler (277, prende l'ultima carta da ogni mano, mescola e redistribuisce), Marc Benioff Mode (278, Leggendaria: tutti +1L).
  - **Economica 272, 274–276, 279–280, 285–286, 292–294, 296–298**: ISV Ecosystem (272, prossimo addon costa 5L fissi), Engagement Score (274, +1L/turno consecutivo con carte max5), Lead Conversion (275, -5L→+1 Elo bonus), Web-to-Lead (276, +1L/avversario non in combat), Salesforce Genie (279, Legg: in combat +3L+2HP; fuori +5L), Salesforce Ohana (280, Legg: tutti +3L+1HP; tu +5L extra), Trailhead Superbadge (285, Legg: traccia 3 boss consecutivi → +1cert+10L), Hyperforce Region (286, Legg: d10 1-3→+3L 4-6→+5L 7-10→+7L), Admin Appreciation Day (292, Admin +5L+draw2; altri +2L), Salesforce Values (293, +2L immediati), Ohana Spirit (294, +2L se tutti alive), Customer Success (296, su prossimo boss defeat watchers +1L), Trailblazer Spirit (297, su boss inedito sconfitto +3L), Salesforce+ Premium (298, draw2+2L).
  - **Manipolazione 273**: Trailhead Quest (273, boss defeat senza carte quel turno → +5L).
  - **Difensiva 288, 295**: NullPointerException (288, se roll==1 in combat round_nullified), Trust First (295, annulla prima Offensiva diretta verso di te).
  - **Offensiva 281, 290, 300**: World's Most Innovative (281, Legg: boss ability disabilitata + threshold=1 + -1HP boss), Lorem Ipsum Boss (290, +2L + bosses_defeated+1), IdeaExchange Champion (300, Legg usa-1: A boss hp=0; B ruba cert; C +10L).
  - **Utilità 282–284, 287, 289, 291, 299**: IdeaExchange Winner (282, Legg: +3L+draw2), Queueable Job (283, Legg: prossime 3 carte ignorano finestre reazione), Bring Your Own Model (284, Legg: in combat +2 roll bonus; fuori +4L), 404 Not Found (287, blocca targeting in/out per 1 turno), Stack Trace (289, recupera fino 3 carte dallo scarto), Copy/Paste (291, +1L+draw1), The Trailbraizer (299, Legg: draw3+5L+hp_full+clear flag negativi).
  - **combat.py hooks**: `null_pointer_active` (288: roll==1→round_nullified one-shot), `boss_threshold_override_1` (281: threshold=1), `trailhead_quest_active` (273: boss defeat senza carte→+5L), `customer_success_active` (296: watchers +1L su boss defeat), `trailblazer_spirit_active` (297: +3L se boss inedito), `superbadge_tracking`+`consecutive_boss_defeats_alive` (285: 3 boss consecutivi→+1cert+10L).
  - **turn.py hooks**: `isv_ecosystem_active` (272: costo addon=5 one-shot), `ohana_truce_caster_id`+`ohana_truce_until_turn` (271: blocca Offensiva verso caster), `trust_first_active` (295: annulla prima Offensiva), `queueable_job_plays_remaining` (283: salta reaction window), `not_found_active` (287: blocca targeting in/out).
  - **end_turn cleanups**: `isv_ecosystem_active`, `trailhead_quest_cards_played`, `not_found_active`+`not_found_until_turn` (se scaduti), `ohana_truce_caster_id`+`ohana_truce_until_turn` (se scaduti).

- [x] **Boss redesign — Batch (27, 31, 33, 38, 40, 41, 44, 45, 50, 52, 53, 54, 56, 58, 64, 65)**
  - **Boss 27**: AoE HP damage cappato ai primi 2 round (era ogni round).
  - **Boss 31**: alla morte del combattente, il boss scarta anche l'addon bloccato (oltre alla penalità normale di morte).
  - **Boss 33**: esplicitato che il numero massimo di carte dichiarabili per round è 2.
  - **Boss 38**: abilità di annullamento ora attiva solo nei round pari (2, 4, 6, …).
  - **Boss 40**: ridotto a 6HP, soglia 5+ (era 8HP/6+).
  - **Boss 41**: nuova abilità "rivela e blocca" — il boss rivela la carta del combattente; gli avversari in ordine di turno possono pagare 1L per bloccarla; la carta viene scartata.
  - **Boss 44**: abilità semplificata — un avversario casuale guadagna +2L all'inizio del combattimento (one-shot).
  - **Boss 45**: nuova abilità "addon licenze drain" — all'inizio di ogni round, se il combattente ha addon attivi ne perde 1L per addon.
  - **Boss 50**: AoE ogni 3 round (era ogni round).
  - **Boss 52**: aggiunta 1 Certificazione alla ricompensa + 🏆.
  - **Boss 53**: nuova abilità "predizione round" — all'inizio del combattimento il giocatore dichiara quanti round durerà; se entro ±1 → +3L, altrimenti -2L.
  - **Boss 54**: nuova meccanica "worst_of_2" — ogni roll tira 2d10 e usa il peggiore.
  - **Boss 56**: nuova meccanica "duplicate roll → auto miss" — ogni numero già tirato in questo combattimento causa miss automatico.
  - **Boss 58**: nuova abilità "soglia random" — ogni round tira 1d4 e la soglia diventa il risultato+6 (7–10); `djinn_threshold` in combat_state.
  - **Boss 64**: nuova abilità "costo crescente" — ogni carta azione giocata in combattimento costa +N licenze cumulative (1ª→+1L, 2ª→+2L, …).
  - **Boss 65**: nuova abilità "predizione direzionale" — ogni round il boss prevede casualmente sopra/sotto 5; se indovina, il combattente perde 1L. Aggiunta 1 Certificazione + 🏆.
  - **engine_boss.py**: aggiornati `apply_boss_ability`, `boss_roll_mode`, `boss_tracks_duplicate_rolls`, `boss_card_play_escalating_cost`, `predicts_roll_direction`, `randomize_threshold`.
  - **combat.py hooks**: `aoe_all_hp_damage` cap round≤2 (27), locked_addon_discard on death (31), `addon_licenze_drain` (45), AoE ogni 3 round (50), `request_round_prediction` at combat_start (53), `worst_of_2` roll mode (54), `lurker_rolled_numbers` duplicate tracking (56), `djinn_threshold` random (58), `stalker_prediction` outcome check -1L (65).
  - **turn.py hooks**: boss 41 reveal-and-block flow, `maelstrom_cards_played_combat` escalating cost (64).
  - **seed_cards.py**: upsert aggiornato per sincronizzare anche `has_certification` e `reward_licenze` su record esistenti.

- [ ] **Rate limiting WS** — un utente non dovrebbe poter inviare messaggi troppo veloci.

---

## 10. TODO e prossimi passi

### Priorità alta

Con `docker compose up --build` il server parte già correttamente:
- migration `0001_initial_schema.py` applicata automaticamente
- seed carte eseguito automaticamente
- FK circolare `winner_id` gestita con `use_alter=True`

### Priorità media

### Priorità bassa (post-MVP)

6. **Frontend** — React + Tailwind (separato, quando il backend è stabile e testato).

7. **Bilanciamento carte** — rivedere HP boss, soglie dado, costi addon, copie nel mazzo dopo le prime partite di test.

8. **Rate limiting WS** — protezione contro spam di messaggi WebSocket.
