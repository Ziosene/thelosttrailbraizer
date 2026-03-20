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
