# Frontend — Changelog

> Registro cronologico di tutte le implementazioni e modifiche al frontend.
> Aggiornato automaticamente ad ogni sessione di sviluppo.

---

## Sessione 1 — Setup iniziale + Login + Lobby

### Setup progetto
- Vite + React 19 + TypeScript 5 scaffoldato
- Tailwind CSS 4 via plugin `@tailwindcss/vite` (no config file separato)
- Zustand 5 per state management, mitt 3 per event bus WebSocket
- Proxy Vite configurato: `/api` → `http://localhost:8000`, `/ws` → `ws://localhost:8000`
- Reset CSS minimale in `index.css`, tema scuro (`bg-slate-950`)

### Architettura base
- **`src/types/game.ts`**: tipi TypeScript completi — `Seniority`, `SENIORITY_HP`, `ROLES` (25 ruoli), `PlayerState`, `GameState`, `AddonInfo`, `BossInfo`, `GameInfo`
- **`src/api/http.ts`**: fetch wrapper con auth header automatico, endpoint `register`, `login`, `me`, `listGames`, `createGame`
- **`src/api/socket.ts`**: WebSocket singleton + event bus `mitt` — `connectSocket`, `sendAction`, `disconnectSocket`, `bus`
- **`src/store/authStore.ts`**: Zustand store con `user`, `token`, `login`, `register`, `logout`, `loadMe` — JWT persistito in `localStorage`

### Componenti UI base
- **`Button.tsx`**: varianti primary/secondary/danger, stato loading
- **`Input.tsx`**: con label, placeholder, stato error

### Componenti Lobby
- **`CharacterSelect.tsx`**: selezione seniority (4 pulsanti con HP) + ruolo (select 25 opzioni) → invia `select_character` via WS
- **`PlayerList.tsx`**: slot giocatori con indicatore ready, highlight utente corrente

### Pagine
- **`LoginPage.tsx`**: tab login/register, gestione errori, redirect automatico
- **`HomePage.tsx`**: creazione partita (2/3/4 giocatori), join per codice, lista partite aperte
- **`LobbyPage.tsx`**: WS connect al mount, selezione personaggio, lista giocatori, avvia partita (host only), redirect su `game_started`

### Routing
- `App.tsx`: router a stato con `Screen` union type — nessuna libreria di routing
- Transizioni automatiche basate su stato auth e eventi WS

---

## Sessione 2 — Fix WebSocket + GamePagePreview

### Fix WebSocket e LobbyPage
- `main.py`: `await websocket.accept()` spostato prima dell'auth check (fix ECONNABORTED)
- `manager.py`: rimosso doppio `accept()` dal metodo `connect`
- `LobbyPage.tsx`: fix parsing `game_state` (`msg.game` non `msg`), optional chaining su `players?.find`, `max_players` aggiunto a `GameState`

### GamePagePreview (`src/pages/GamePagePreview.tsx`)
- Bozza layout completa schermata di gioco
- Layout griglia 2/3/4 giocatori: quadranti uguali (flex-1) senza addon, si allungano e scrollano con addon
- Addon con CSS float attorno alla card giocatore (wrapping naturale, no spazi vuoti)
- Sidebar sinistra fissa: addon mercato, mazzi azioni (viola/blu), mazzi addon (verde/teal) — grafica carte impilate con pulsante Pesca
- Sidebar destra fissa: boss attivi con HP/threshold, mazzi boss (arancione/rosso) — stessa grafica
- Overlay carta al click (qualsiasi carta: addon, boss, mano, mercato)
- Mano in strip fissa in fondo
- Log panel toggle a destra
- JWT ridotto da 7 giorni a 1 giorno (`access_token_expire_minutes = 1440`)

---

## Sessione 3 — GamePage reale + gameStore

### Backend: `game_helpers.py`
- `_build_game_state`: aggiunta lista pubblica `addons` per ogni giocatore (`player_addon_id`, `addon_id`, `name`, `is_tapped`)

### Tipi: `src/types/game.ts` (refactor completo)
- Aggiunti: `HandCard`, `HandAddon`, `PublicAddon`, `BossMarketInfo`, `AddonMarketInfo`
- `PlayerState` aggiornato: `addon_count`, `is_in_combat`, `bosses_defeated`, `trophies`, `addons: PublicAddon[]`
- `GameState` aggiornato: tutti i campi reali backend (`turn_number`, `current_phase`, deck counts, mercati come oggetti)
- Rimosso `AddonInfo` (sostituito da `PublicAddon` e `HandAddon`)
- Mantenuti `GameInfo` e `BossInfo` per compatibilità LobbyPage

### Store: `src/store/gameStore.ts` (nuovo)
- Zustand store per la partita: `gameState`, `hand`, `myAddons`, `combatActive`
- `connect(gameCode, userId)`: apre WS, sottoscrive `game_state`, `hand_state`, `combat_started`, `combat_ended`
- `disconnect()`: chiude WS, svuota bus, resetta stato
- `send(action, data)`: wrapper su `sendAction`

### Pagina: `src/pages/GamePage.tsx` (nuovo)
- Layout identico a `GamePagePreview` con dati reali
- `LeftSidebar`: addon mercato (2 slot con pulsante Acquista), mazzi azioni (Pesca 1/2), mazzi addon (Pesca 1/2)
- `BossSidebar`: boss attivi (2 slot con pulsante Affronta), mazzi boss (count reale, no pulsante Pesca boss)
- `PlayerCell`: dati reali `PlayerState`, addons pubblici da `player.addons` (PublicAddon[]), tappati = opacity-35 grayscale
- `PlayArea`: layout 2P/3P/4P con rotazione automatica giocatori (io sempre in basso)
- Header: turno numero reale, fase corrente, indicatore "Tu" vs nickname corrente
- Mano: strip carte reali da `hand` (HandCard[]), pulsante Gioca → `play_card`
- Azioni: `end_turn`, `play_card`, `buy_addon`, `start_combat`, `draw_action`, `draw_addon`
- Loading state: spinner animato se `gameState === null`
- `CardOverlay`: click su qualsiasi carta → ingrandita al centro

### Routing: `src/App.tsx`
- `screen.name === 'game'` ora renderizza `<GamePage gameCode={screen.code} />` invece di `GamePagePreview`

---

## Sessione 4 — GamePage layout aggiornato (sync con GamePagePreview)

### Pagina: `src/pages/GamePage.tsx` (refactor layout)
- `DeckRow` sostituito con `DeckCard`: stessa grafica carte impilate proporzionali (W=62, H=90) usata in preview
- `LeftSidebar`: rimossi mazzi azioni/addon — ora contiene solo "Addon mercato"
- `BossSidebar`: rimosso mazzo boss — ora contiene solo "Boss attivi"
- Sezione mano in fondo: refactoring con layout flex orizzontale
  - Sinistra flex-1: carte in mano scrollabili orizzontalmente
  - Divisore verticale
  - Destra shrink-0: 3 gruppi di DeckCard (Azioni/Addon/Boss) con titoli categoria
  - Boss deck senza onDraw (pesca boss non implementata lato server)
- `PlayerCell`: aggiunto `🃏 N in mano` nella info card del giocatore (usa `p.hand_count`)
- `PlayArea` e `GamePage`: rimossi tutti i deck props non più necessari (`actionDeck1Count`, `addonDeck1Count`, `bossDeck1Count`, ecc.)

---

## Sessione 5 — Modal interattivi (reazione + scelta carta)

### Store: `src/store/gameStore.ts`
- Aggiunti tipi: `PendingChoice`, `ReactionWindow` (esportati)
- Aggiunto stato: `pendingChoice`, `reactionWindow`
- Nuove azioni `connect()`: sottoscrive `card_choice_required`, `reaction_window_open`, `reaction_window_closed`
- Aggiunta azione `clearPendingChoice()` per resettare dopo submit

### Componenti: `src/components/game/GameModals.tsx` (nuovo)
- **`ReactionWindowModal`**: overlay bottom con countdown (8s), lista carte in mano cliccabili → `play_reaction`, pulsante Passa → `pass_reaction`; countdown diventa rosso/animato negli ultimi 3 secondi
- **`CardChoiceModal`**: gestisce tutti e 8 i `choice_type`:
  - `discard_specific_cards`: selezione multipla di N carte dalla mano (hand_card_id)
  - `return_card_to_deck_top`: selezione singola dalla mano (hand_card_id)
  - `keep_one_from_drawn`: selezione singola tra le carte pescate (action_card_id)
  - `choose_cards_to_keep`: selezione multipla fino a max_keep (hand_card_id)
  - `recover_from_discard`: selezione multipla dal discard pile (action_card_id, nomi "Carta #ID")
  - `choose_addon_to_return`: selezione singola tra myAddons (player_addon_id)
  - `reorder_action_deck` / `reorder_boss_deck`: lista riordinabile con frecce su/giù

### Pagina: `src/pages/GamePage.tsx`
- Importati e renderizzati `ReactionWindowModal` e `CardChoiceModal`
- `send('card_choice', ...)` + `clearPendingChoice()` al submit del modal

---

## Sessione 6 — Log live, fix card play, refactor GamePage in componenti

### Store: `src/store/gameStore.ts`
- Aggiunto tipo `LogEntry` (esportato): `{ id, time, text, color }`
- Aggiunto stato `log: LogEntry[]` (max 200 entry, newest-first)
- `connect()` ora sottoscrive ~20 eventi WS e aggiunge entry al log con colori per tipo
- Aggiunto `card_name?: string` in `PendingChoice` (nome carta che ha generato la scelta)

### Tipi: `src/types/game.ts`
- `PublicAddon`: aggiunto campo `effect: string`
- `BossMarketInfo`: aggiunti campi `ability: string`, `reward_licenze: number`, `difficulty: string`

### Backend fix: `card_play.py` (via sessione precedente)
- Fix `UnboundLocalError: card` — spostato blocco validazione `when` dopo assegnazione `card`
- Fix `UnboundLocalError: card_effect_result` — aggiunto `card_effect_result = None` prima dei blocchi condizionali
- Fix pending_choice: aggiunto `await _send_hand_state(...)` PRIMA di `card_choice_required` — così il client ha le carte pescate prima che il modal si apra
- Aggiunto `card_name` nell'evento `card_choice_required`

### Componenti game (nuovi file da refactor GamePage):
- **`CardVisual.tsx`**: `CardInfo` type, `CardVisual`, `CardOverlay`, `DeckCard`, `HandCardVisual`
- **`PlayerCell.tsx`**: `HP`, `Certs`, `Corner` type, `PlayerCell`
- **`PlayArea.tsx`**: `LeftSidebar`, `BossSidebar`, `PlayArea`, `CellData` type
- **`HandPanel.tsx`**: `HandPanel` — mano giocatore + 3 gruppi DeckCard (Azioni/Addon/Boss)
- **`LogPanel.tsx`**: `LogPanel` — pannello log toggle

### Pagina: `src/pages/GamePage.tsx` (refactor)
- Ridotta a ~140 righe di pura orchestrazione
- Tutta la logica UI estratta nei componenti `game/`
- Header semplificato: rimosso `phaseLabel` intermedio, turnLabel reso inline

---

## Sessione 7 — Sezione mazzi con modale + Toast errori

### Backend: `app/websocket/game_helpers.py`
- `_build_game_state` ora espone per ogni tipo di pila scarti:
  - `action_discard_count`, `action_discard_top` (`{id, name, card_type, rarity}`)
  - `boss_graveyard_count`, `boss_graveyard_top` (`{id, name, difficulty}`)
  - `addon_graveyard_count`, `addon_graveyard_top` (`{id, name, rarity}`)
  - I campi `*_top` sono `null` se la pila è vuota

### Tipi: `src/types/game.ts`
- Aggiunti: `DiscardTopAction`, `DiscardTopBoss`, `DiscardTopAddon`
- `GameState` aggiornato con i 6 nuovi campi discard/graveyard

### Componente: `src/components/game/DeckModal.tsx` (nuovo)
- Modale centrata aperta da HandPanel (uno per tipo: action/addon/boss)
- Mostra Mazzo 1 e Mazzo 2 (cliccabili per pesca solo Azioni in fase draw)
- Mostra Scarti: ultima carta con nome + sottotitolo, oppure `∅ vuoto`
- Pulsante Azioni pulsa amber se è il turno del giocatore in fase draw

### Componente: `src/components/game/HandPanel.tsx` (refactor sezione mazzi)
- Sostituiti 6 `DeckCard` con 3 pulsanti: `⚡ Azioni`, `🔧 Addon`, `👾 Boss`
- Ogni pulsante mostra totale carte nei due mazzi
- Click → apre `DeckModal` per quel tipo
- Pulsante Azioni pulsa amber in fase draw

### Store: `src/store/gameStore.ts`
- Aggiunto tipo `Toast` (esportato): `{ id, message }`
- Aggiunto stato `toasts: Toast[]`
- Aggiunta azione `removeToast(id)`
- `bus.on('error')` ora chiama sia `addLog` che `addToast`

### Componente: `src/components/game/ToastLayer.tsx` (nuovo)
- Renders stack toast fixed top-right (z-index 100)
- Auto-dismiss dopo 4 secondi via `useEffect` + `setTimeout`
- Chiudibile manualmente con `×`
- Sfondo `red-950`, bordo `red-700/60`

### Pagina: `src/pages/GamePage.tsx`
- Aggiunto `<ToastLayer />` al render root

## Sessione 8 — Debug Mode addon, carta 189 scelta addon, smoke test carte, fix bug

### Backend: `app/game/engine_cards/interferenza.py`
- Carta 189 (Delete Records): restituisce `pending_choice` con `choice_type: "delete_target_addon"` + lista `target_addon_options`; se target senza addon → `applied=False` con reason `target_has_no_addons`
- Fix carte 222 (Block Kit), 229 (SLA Tier), 237 (Dataflow): `get_target()` ora passa `player` come secondo argomento (era omesso → TypeError)

### Backend: `app/game/engine_cards/offensiva.py`
- Fix carta 194 (Assignment Element): `get_target()` ora passa `player` come secondo argomento

### Backend: `app/game/engine_cards/utilita.py`
- Fix carta 215 (B2B Analytics), 270 (Success Community): `get_target()` ora passa `player`
- Fix carta 196 (Get Records): `game.boss_deck` → `game.boss_deck_1 or boss_deck_2`
- Fix carta 248 (Pipeline Promotion): `game.boss_deck` → `game.boss_deck_1 or boss_deck_2`
- Fix carta 266 (Salesforce Ben): `game.boss_deck` → `game.boss_deck_1 or boss_deck_2`

### Backend: `app/websocket/handlers/turn/play/card_play.py`
- `applied=False` → invia toast di errore al giocatore con messaggio in italiano (mappatura reason)

### Backend: `app/websocket/handlers/turn/play/choices.py`
- Aggiunto resolver `delete_target_addon`: valida `player_addon_id`, rimuove addon dal target, aggiunge a `addon_graveyard`

### Backend: `app/websocket/handlers/turn/addons/combat.py` + `callbacks.py`
- Addon 9 (Debug Mode): flusso peek boss dal mazzo → evento `debug_mode_peek` → scelta fight/send_back

### Store: `src/store/gameStore.ts`
- Aggiunto `DebugModePeek` interface e stato `debugModePeek`
- Aggiunto `TargetAddonOption` interface
- `PendingChoice` esteso con `target_addon_options?: TargetAddonOption[]`
- `bus.on('debug_mode_peek')` → setta `debugModePeek`

### Componente: `src/components/game/GameModals.tsx`
- `DebugModeModal` (nuovo): mostra statistiche boss + abilità, pulsanti ⚔️ Combatti / ↩ Rimanda
- `CardChoiceModal` esteso: gestisce `choice_type: "delete_target_addon"` con lista addon selezionabile

### Pagina: `src/pages/GamePage.tsx`
- Aggiunto `<DebugModeModal>` al render root

### Test: `backend/tests/engine_cards/test_all_cards_smoke.py` (nuovo)
- Smoke test parametrizzato su tutte le 300 carte (3 varianti: happy-path, no-target, target-senza-addon)
- Risultato: **597 passed, 303 skipped, 0 failed**
- `KNOWN_SKIP`: 101 carte (solo in combattimento, target in combattimento, reazione, discard_empty, condizioni speciali)
