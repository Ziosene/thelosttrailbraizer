import { create } from 'zustand'
import { bus, connectSocket, disconnectSocket, sendAction } from '../api/socket'
import type { GameState, HandCard, HandAddon } from '../types/game'

export interface PendingChoice {
  choice_type: string
  card_number: number
  card_name?: string
  options?: number[]
  count?: number
  drawn_card_ids?: number[]
  boss_card_ids?: number[]
  action_card_ids?: number[]
  max_keep?: number
  licenze_gained?: number
}

export interface ReactionWindow {
  trigger_card: { id: number; name: string }
  attacker_player_id: number
  timeout_ms: number
  opened_at: number
}

export interface ComplyOrRefuse {
  caster_player_id: number
  comply_cost: number
  refuse_cost: number
  opened_at: number
}

export interface LogEntry {
  id: number
  time: string
  text: string
  color: string
}

let _logSeq = 0
function mkEntry(text: string, color = 'text-slate-400'): LogEntry {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  return { id: _logSeq++, time, text, color }
}

interface GameStore {
  gameCode: string | null
  myUserId: number | null
  gameState: GameState | null
  hand: HandCard[]
  myAddons: HandAddon[]
  combatActive: boolean
  pendingChoice: PendingChoice | null
  reactionWindow: ReactionWindow | null
  complyOrRefuse: ComplyOrRefuse | null
  log: LogEntry[]
  connect: (gameCode: string, userId: number) => void
  disconnect: () => void
  send: (action: string, data?: Record<string, unknown>) => void
  clearPendingChoice: () => void
}

export const useGameStore = create<GameStore>((set, get) => {
  // Helper: resolve player nickname from current gameState
  const pName = (id: number): string => {
    const p = get().gameState?.players.find(p => p.id === id)
    return p ? p.nickname : `#${id}`
  }

  const addLog = (text: string, color = 'text-slate-400') => {
    set(s => ({ log: [mkEntry(text, color), ...s.log].slice(0, 200) }))
  }

  return {
    gameCode: null,
    myUserId: null,
    gameState: null,
    hand: [],
    myAddons: [],
    combatActive: false,
    pendingChoice: null,
    reactionWindow: null,
    complyOrRefuse: null,
    log: [],

    connect(gameCode, userId) {
      set({ gameCode, myUserId: userId })
      const ws = connectSocket(gameCode)
      ws.onopen = () => sendAction('join_game', { game_code: gameCode })

      bus.on('game_state', (msg: any) => set({ gameState: msg.game }))
      bus.on('hand_state', (msg: any) => {
        set({ hand: msg.hand ?? [], myAddons: msg.addons ?? [] })
      })

      bus.on('game_started', () => {
        addLog('⚡ Partita iniziata!', 'text-violet-400')
      })
      bus.on('turn_started', (msg: any) => {
        addLog(`↩ Turno di ${pName(msg.player_id)}`, 'text-slate-300')
      })
      bus.on('card_drawn', (msg: any) => {
        const who = pName(msg.player_id)
        if (msg.suppressed) addLog(`${who} vuole pescare ma viene soppresso`, 'text-slate-500')
        else addLog(`${who} pesca una carta`)
      })
      bus.on('card_played', (msg: any) => {
        const who = pName(msg.player_id)
        const card = msg.card?.name ?? '?'
        addLog(`${who} gioca "${card}"`, 'text-blue-400')
      })
      bus.on('addon_bought', (msg: any) => {
        const who = pName(msg.player_id)
        const name = msg.addon?.name ?? '?'
        addLog(`${who} acquista addon "${name}"`, 'text-emerald-400')
      })
      bus.on('addon_used', (msg: any) => {
        addLog(`${pName(msg.player_id)} attiva un addon`, 'text-teal-400')
      })
      bus.on('combat_started', (msg: any) => {
        set({ combatActive: true })
        const boss = msg.boss?.name ?? '?'
        addLog(`⚔️ ${pName(msg.player_id)} affronta "${boss}"`, 'text-orange-400')
      })
      bus.on('dice_rolled', (msg: any) => {
        const hit = msg.result === 'hit'
        addLog(
          `🎲 ${pName(msg.player_id)} tira ${msg.roll} → ${hit ? 'COLPITO!' : 'mancato'}`,
          hit ? 'text-green-400' : 'text-red-400',
        )
      })
      bus.on('combat_ended', (msg: any) => {
        set({ combatActive: false })
        if (msg.boss_defeated) addLog(`🏆 Boss sconfitto da ${pName(msg.player_id)}!`, 'text-yellow-400')
        else if (msg.player_died) addLog(`💀 ${pName(msg.player_id)} è morto in combattimento`, 'text-red-500')
        else addLog(`🏃 ${pName(msg.player_id)} si ritira dal combattimento`, 'text-slate-400')
      })
      bus.on('player_died', (msg: any) => {
        addLog(`💀 ${pName(msg.player_id)} muore (penalità applicata)`, 'text-red-500')
      })
      bus.on('turn_ended', (msg: any) => {
        addLog(`✓ Fine turno di ${pName(msg.player_id)}`, 'text-slate-500')
      })
      bus.on('game_over', (msg: any) => {
        addLog(`🎉 Partita finita! Vince ${pName(msg.winner_id)}`, 'text-yellow-300')
      })
      bus.on('reaction_resolved', (msg: any) => {
        if (msg.reactor_player_id) {
          const cancelled = msg.original_cancelled ? ' (carta originale annullata)' : ''
          addLog(`⚡ ${pName(msg.reactor_player_id)} reagisce${cancelled}`, 'text-amber-400')
        }
      })
      bus.on('player_joined', (msg: any) => {
        addLog(`${msg.nickname} entra in partita`, 'text-slate-500')
      })
      bus.on('player_left', (msg: any) => {
        addLog(`Giocatore #${msg.user_id} lascia la partita`, 'text-slate-500')
      })
      bus.on('error', (msg: any) => {
        addLog(`⚠ ${msg.message}`, 'text-red-400')
      })
      bus.on('roles_swapped', (msg: any) => {
        addLog(
          `🔄 ${pName(msg.player_id)} e ${pName(msg.target_player_id)} scambiano ruoli`,
          'text-purple-400',
        )
      })
      bus.on('borrowed_passive_active', (msg: any) => {
        addLog(
          `🎭 ${pName(msg.player_id)} usa la passiva di ${msg.borrowed_role}`,
          'text-purple-400',
        )
      })

      bus.on('card_choice_required', (msg: any) => {
        const { type: _t, ...rest } = msg
        set({ pendingChoice: rest as PendingChoice })
      })
      bus.on('reaction_window_open', (msg: any) => {
        set({ reactionWindow: { ...msg, opened_at: Date.now() } })
      })
      bus.on('reaction_window_closed', () => set({ reactionWindow: null }))
      bus.on('card115_comply_or_refuse', (msg: any) => {
        set({ complyOrRefuse: { ...msg, opened_at: Date.now() } })
        addLog(
          `🔔 Richiesta licenza da ${pName(msg.caster_player_id)}: paga ${msg.comply_cost}L o rifiuta (${msg.refuse_cost}L)`,
          'text-amber-400',
        )
      })
    },

    disconnect() {
      bus.all.clear()
      disconnectSocket()
      set({
        gameCode: null, gameState: null, hand: [], myAddons: [],
        combatActive: false, pendingChoice: null, reactionWindow: null, complyOrRefuse: null, log: [],
      })
    },

    send(action, data = {}) {
      sendAction(action, data)
    },

    clearPendingChoice() {
      set({ pendingChoice: null })
    },
  }
})
