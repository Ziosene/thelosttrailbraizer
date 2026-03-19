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

> Per il dettaglio di ogni implementazione vedere [CHANGELOG.md](CHANGELOG.md).

### ✅ Completato

- Modelli DB, Auth JWT, API REST, WebSocket
- Game Engine: tutte le funzioni pure (roll, combat, death, deck, victory, ELO)
- Sistema abilità boss: tutti i 100 boss cablati (engine_boss.py + combat.py + turn.py)
- Effetti carte azione: tutte le 300 carte implementate (engine_cards/)
- Sistema reazione out-of-turn (reaction_manager.py)
- Docker + Alembic migrations (0001–0005) + seed idempotente
- Bilanciamento boss: redesign batch 1 (boss 27, 31, 33, 38, 40, 41, 44, 45, 50, 52, 53, 54, 56, 58, 64, 65) + aggiustamenti puntuali (67, 68, 70, 81, 87, 91, 92, 93, 97, 100)
- Effetti addon 1–20: implementati (batch 1)
- Effetti addon 21–41: implementati (batch 2)
- Effetti addon 42–67: implementati (batch 3)
- Effetti addon 68–90: implementati (batch 4) — addon 68/69 (theft protection) in engine_cards/economica.py; addon 70 (einstein insights), 71 (first card free), 72 (process chain), 73 (trigger handler), 74 (save hook), 75 (cascade untap), 76 (rollup defeats), 77 (formula field +roll/+dmg), 78 (validation rule draw2), 79 (auto-response retaliation), 80 (field dependency discount), 81 (vuln scan +4 roll), 82/85 (boss freeze/refresh), 83 (sandbox preview), 84 (governor cap boss hp4), 86 (critical patch +1L on miss), 87 (throttle bypass), 88 (mass update 2dmg), 89 (data migration swap), 90 (org split hp)
- Effetti addon 91–110: implementati (batch 5) — 91 (free trial borrow/return), 92 (beta feature reject/keep), 93 (pilot program pick from graveyard), 94 (release train every 4 turns), 95 (sprint review swap), 96 (backlog refinement peek), 97 (definition of done +2L at full HP), 98 (acceptance criteria simplified: always 2 cards), 99 (retrospective discard 2 from target), 100 (kanban board hand12), 101 (org-wide sharing +1L), 102 (custom permission TODO pending role system), 103 (named credential interferenza immunity), 104 (user story draw3+gain3L), 105 (epic feature streak cert), 106 (story points boss.hp L), 107 (tech debt idle addon L), 108 (architecture review return+8L), 109 (proof of concept free card slot), 110 (go-live celebration all+1L)
- Nuove client action: `beta_feature_reject`, `beta_feature_keep`, `pilot_program_pick`, `acceptance_criteria_choose`

### ⬜ Da fare

- [ ] **Effetti addon 111–200** — da implementare.
- [ ] **Addon 98 (Acceptance Criteria)** — implementato in versione semplificata (sempre 2 carte, niente scelta asincrona). Se serve la scelta interattiva, richiede refactor del boss defeat flow.
- [ ] **Addon 76 (Rollup Summary)** — contatore `rollup_boss_defeats` in combat_state pronto; mancante integrazione ELO finale.
- [ ] **Validazione timing carte** — campo `Quando` da verificare in `_handle_play_card`.
- [ ] **Validazione timing carte** — campo `Quando` da verificare in `_handle_play_card`.
- [ ] **Rate limiting WS** — protezione contro spam di messaggi WebSocket.

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

7. **Bilanciamento carte** — prima revisione completa effettuata (carte azione 1–300 e addon 1–200). Ulteriore ribilanciamento previsto dopo le prime partite di test.

8. **Rate limiting WS** — protezione contro spam di messaggi WebSocket.
