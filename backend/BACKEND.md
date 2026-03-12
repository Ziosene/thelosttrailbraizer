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
│       └── 0001_initial_schema.py ✅ schema completo + FK circolare risolta
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
│   │   └── game_handler.py       ✅ routing completo incluso use_addon + ELO end-game
│   └── game/
│       ├── __init__.py           ✅
│       └── engine.py             ✅ funzioni pure + ELO (update_elo, expected_score)
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
- **engine.py** contiene solo funzioni pure (testabili senza DB), chiamate dal `game_handler`.
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

FINE TURNO
  └─ untap tutti gli addon del giocatore
  └─ reset cards_played_this_turn = 0
  └─ indice avanza al prossimo giocatore
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

### ⬜ Da fare

- [ ] **Effetti carte azione (300 carte)** — `_handle_play_card` rimuove la carta dalla mano ma NON applica nessun effetto. Va creata una funzione `apply_action_card_effect(card, player, game, db)` in `engine.py` con un branch per ognuna delle 300 carte (o per famiglia di effetto). Vedere `cards/action_cards.md`. Categorie:
  - Economiche: guadagna/trasferisci licenze con condizioni
  - Offensive: danno immediato o persistente al boss
  - Difensive: recupero HP, scudi, blocco danno
  - Manipolazione dado: modifica soglia, ritiro, forza valore
  - Utilità: pesca carte, riordina/recupera mazzi
  - Interferenza: azioni forzate su avversari, furti
  - Leggendarie: effetti compositi multi-categoria
  - **Validazione timing** — ogni carta ha un campo `Quando` che va verificato prima di giocarla (es. "durante combattimento", "fuori dal combattimento"). Da implementare in `can_play_card(card, game)`.

- [ ] **Effetti addon (200 addon)** — `_handle_use_addon` tappa l'addon ma NON applica nessun effetto. Va creata `apply_addon_effect(addon, player, game, db)` per gli addon Attivi (uso manuale) e hook `trigger_passive_addons(event, player, game, db)` nei seguenti punti del flusso:
  - `on_draw` — in `_handle_draw_card` dopo aver pescato
  - `on_turn_end` — in `_handle_end_turn` prima di untappare gli addon
  - `on_addon_bought` — in `_handle_buy_addon` dopo l'acquisto
  - `on_roll` — in `_handle_roll_dice` prima/dopo il tiro dado
  Vedere `cards/addon_cards.md` per l'effetto completo di ogni addon.

- [ ] **Abilità speciali boss (100 boss)** — `_handle_roll_dice` non applica nessuna abilità speciale del boss. Va creata `apply_boss_ability(boss, player, game, roll, trigger, db)` con trigger `"before_roll"` / `"after_roll"` / `"on_survive"`. Vedere `cards/boss_cards.md` per l'abilità di ogni boss.

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
