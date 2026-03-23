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
