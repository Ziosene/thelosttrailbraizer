# Frontend — The Lost Trailbraizer

> Documentazione tecnica del frontend. Aggiornata ad ogni modifica.

---

## 1. Stack

| Tecnologia | Versione | Scopo |
|------------|----------|-------|
| React | 19 | UI component framework |
| TypeScript | 5 | Type safety |
| Vite | 6 | Dev server + build |
| Tailwind CSS | 4 | Styling utility-first |
| Zustand | 5 | State management globale |
| mitt | 3 | Event bus WebSocket |

---

## 2. Avvio

```bash
cd frontend
npm install
npm run dev        # dev server su http://localhost:5173
npm run build      # build produzione in dist/
npm run preview    # preview build produzione
```

Il backend deve girare su `localhost:8000` (via `docker compose up --build`).
Il proxy Vite gestisce automaticamente CORS:
- `/api/*` → `http://localhost:8000/*`
- `/ws/*` → `ws://localhost:8000/*`

---

## 3. Struttura cartelle

```
frontend/
├── public/                  asset statici (favicon, icons.svg)
├── src/
│   ├── api/
│   │   ├── http.ts          client HTTP (fetch wrapper + endpoint REST)
│   │   └── socket.ts        WebSocket singleton + event bus mitt
│   ├── store/
│   │   ├── authStore.ts     stato autenticazione (Zustand): user, token, login, logout
│   │   └── gameStore.ts     stato partita (Zustand): gameState, hand, myAddons, connect, disconnect, send
│   ├── types/
│   │   └── game.ts          tipi TypeScript: PlayerState, GameState, HandCard, HandAddon, PublicAddon, BossMarketInfo, AddonMarketInfo, Seniority, Role
│   ├── components/
│   │   ├── ui/
│   │   │   ├── Button.tsx   bottone con varianti (primary, secondary, danger) e stato loading
│   │   │   └── Input.tsx    input con label, placeholder, stato error
│   │   ├── lobby/
│   │   │   ├── CharacterSelect.tsx  selezione seniority (con HP) + ruolo (dropdown)
│   │   │   └── PlayerList.tsx       lista giocatori in lobby con stato ready/non-ready
│   │   └── game/
│   │       ├── CardVisual.tsx   CardInfo type, CardVisual, CardOverlay, DeckCard, HandCardVisual
│   │       ├── PlayerCell.tsx   HP, Certs, Corner type, PlayerCell
│   │       ├── PlayArea.tsx     LeftSidebar, BossSidebar, PlayArea, CellData type
│   │       ├── HandPanel.tsx    mano + gruppi mazzi (HandPanel)
│   │       ├── LogPanel.tsx     pannello log partita (LogPanel)
│   │       └── GameModals.tsx   ReactionWindowModal, CardChoiceModal
│   ├── pages/
│   │   ├── LoginPage.tsx        login + registrazione (tab switch)
│   │   ├── HomePage.tsx         crea partita, unisciti con codice, lista partite aperte
│   │   ├── LobbyPage.tsx        lobby pre-partita: selezione personaggio + lista giocatori + avvia
│   │   ├── GamePage.tsx         orchestrazione schermata di gioco (thin, ~140 righe)
│   │   └── GamePagePreview.tsx  bozza layout con dati mock (da eliminare dopo validazione)
│   ├── App.tsx              router basato su stato (Screen union type, no libreria router)
│   ├── index.css            reset base + import Tailwind
│   └── main.tsx             entry point React
├── vite.config.ts           config Vite + proxy backend
├── tsconfig.app.json
└── package.json
```

---

## 4. Navigazione

Nessuna libreria di routing — navigazione gestita con uno stato `Screen` in `App.tsx`:

```ts
type Screen =
  | { name: 'login' }
  | { name: 'home' }
  | { name: 'lobby'; code: string }
  | { name: 'game'; code: string }
```

Transizioni automatiche:
- Token presente → `home` (al mount, via `loadMe()`)
- Login riuscito → `home`
- Logout → `login`
- Crea/entra partita → `lobby`
- `game_started` WS event → `game`

---

## 5. Autenticazione

- JWT salvato in `localStorage` con chiave `token`
- `authStore.ts` (Zustand) espone: `user`, `token`, `login()`, `register()`, `logout()`, `loadMe()`
- `http.ts` legge automaticamente il token da localStorage e lo aggiunge all'header `Authorization: Bearer`
- Al mount di `App.tsx`, se c'è un token salvato viene chiamato `loadMe()` per ripristinare la sessione

---

## 6. WebSocket

`socket.ts` gestisce un singolo WebSocket attivo alla volta:

```ts
connectSocket(gameCode)   // apre WS, invia token come query param
sendAction(action, data)  // invia messaggio al server
disconnectSocket()        // chiude WS
bus                       // mitt EventEmitter — emette ogni messaggio ricevuto per type
```

Il backend invia ~70 tipi di evento. I componenti si sottoscrivono con:
```ts
bus.on('game_state', handler)
bus.on('card_choice_required', handler)
// ...
```

Sempre fare `bus.off(...)` nel cleanup `useEffect`.

---

## 7. API REST

Tutti gli endpoint passano per `api` in `http.ts`:

| Metodo | Path | Scopo |
|--------|------|-------|
| POST | `/auth/register` | Registrazione |
| POST | `/auth/login` | Login → JWT |
| GET | `/auth/me` | Profilo utente corrente |
| GET | `/games` | Lista partite in attesa |
| POST | `/games` | Crea nuova partita |

---

## 8. Tipi principali (`types/game.ts`)

| Tipo | Descrizione |
|------|-------------|
| `Seniority` | `'Junior' \| 'Experienced' \| 'Senior' \| 'Evangelist'` |
| `SENIORITY_HP` | Map seniority → HP (J=1, E=2, S=3, Ev=4) |
| `ROLES` | Array readonly dei 25 ruoli disponibili |
| `PlayerState` | Stato di un giocatore (id, hp, licenze, cert, hand_count, addons…) |
| `GameState` | Stato completo partita (players, mercati, current_player_id…) |
| `HandCard` | Carta in mano: `hand_card_id`, `card_id`, `name`, `card_type`, `effect`, `rarity` |
| `HandAddon` | Addon in mano: `player_addon_id`, `addon_id`, `name`, `addon_type`, `effect`, `is_tapped` |
| `PublicAddon` | Addon visibile a tutti: `player_addon_id`, `addon_id`, `name`, `effect`, `is_tapped` |
| `BossMarketInfo` | Boss in market: `id`, `name`, `hp`, `threshold`, `ability`, `reward_licenze`, `difficulty` |
| `AddonMarketInfo` | Addon in market: `id`, `name`, `cost`, `effect`, `rarity` |
| `BossInfo` | (legacy LobbyPage) Boss con hp, dice_threshold, has_certification, reward_licenze |

---

## 9. Schermate implementate

### LoginPage
- Tab login / registrazione
- Campi nickname + password
- Errori inline
- Redirect automatico a home se già autenticati

### HomePage
- Selezione numero giocatori (2/3/4)
- Creazione partita → redirect a lobby
- Join per codice partita (input + bottone)
- Lista partite aperte in tempo reale (polling al mount)

### LobbyPage
- Connessione WebSocket al mount (`join_game`)
- `CharacterSelect`: scelta seniority (4 pulsanti con HP) + ruolo (select con 25 opzioni) → invia `select_character`
- `PlayerList`: slot giocatori con indicatore ready (verde/grigio), highlight "tu"
- Pulsante "Avvia partita" visibile solo all'host, abilitato solo se tutti pronti e ≥2 giocatori
- Redirect automatico a `game` su evento `game_started`

### GamePagePreview (bozza layout)
- Layout responsivo 2/3/4 giocatori con griglia uguale per quadrante
- **Sidebar sinistra** (fissa, `w-48`): addon mercato (2 carte acquistabili), mazzo azioni (Mazzo 1/2 con grafica carte impilate + pulsante Pesca), mazzo addon (Mazzo 1/2 stessa grafica)
- **Sidebar destra** (fissa, `w-48`): boss attivi (2 carte boss con HP/threshold/Affronta), mazzo boss (Mazzo 1/2 con grafica carte impilate + pulsante Pesca)
- **Griglia giocatori**: quadranti uguali quando pochi addon (`flex-1`), si allungano e scrollano quando gli addon crescono
- **Addon**: flow con CSS `float` attorno alla card giocatore (wrapping naturale), direzione per giocatore (L→R: Mario/Luca, R→L: Sara/Tu)
- **Overlay carta**: click su qualsiasi carta (addon, boss, mano, mercato) apre overlay grande al centro
- **Mano**: strip in fondo con carte giocabili
- **Log**: pannello toggle a destra

---

## 10. Da fare

- [x] **GamePage** — implementazione reale con dati WS (gameStore, hand, combat)
- [x] **gameStore** — stato partita in Zustand (game_state, hand privata, log, pendingChoice, reactionWindow)
- [x] **Modal interattivi** — ReactionWindowModal + CardChoiceModal (tutti 8 choice_type)
- [x] **Log partita** — panel toggle con tutti gli eventi WS in tempo reale
- [x] **CardOverlay** — overlay ingrandita con descrizione effetto + pulsante azione
- [x] **GamePage refactor** — suddivisa in componenti: CardVisual, PlayerCell, PlayArea, HandPanel, LogPanel
- [ ] **Abilità passiva ruolo** — mostrare descrizione ruolo nella lobby in CharacterSelect
- [ ] **Toast / notifiche** — feedback visivo per eventi WS (boss sconfitto, carta giocata, ecc.)
- [ ] **Modal combattimento** — tiro dado, dichiarazione carta per boss 33/86
- [ ] **Game over screen** — schermata finale con vincitore + statistiche
