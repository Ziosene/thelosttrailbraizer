import { create } from 'zustand'
import { bus, connectSocket, disconnectSocket, sendAction } from '../api/socket'
import type { GameState, HandCard, HandAddon } from '../types/game'

export interface PendingChoice {
  choice_type: string
  card_number: number
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

interface GameStore {
  gameCode: string | null
  myUserId: number | null
  gameState: GameState | null
  hand: HandCard[]
  myAddons: HandAddon[]
  combatActive: boolean
  pendingChoice: PendingChoice | null
  reactionWindow: ReactionWindow | null
  connect: (gameCode: string, userId: number) => void
  disconnect: () => void
  send: (action: string, data?: Record<string, unknown>) => void
  clearPendingChoice: () => void
}

export const useGameStore = create<GameStore>((set) => ({
  gameCode: null,
  myUserId: null,
  gameState: null,
  hand: [],
  myAddons: [],
  combatActive: false,
  pendingChoice: null,
  reactionWindow: null,

  connect(gameCode, userId) {
    set({ gameCode, myUserId: userId })
    const ws = connectSocket(gameCode)
    ws.onopen = () => sendAction('join_game', { game_code: gameCode })

    bus.on('game_state', (msg: any) => set({ gameState: msg.game }))
    bus.on('hand_state', (msg: any) => {
      set({ hand: msg.hand ?? [], myAddons: msg.addons ?? [] })
    })
    bus.on('combat_started', () => set({ combatActive: true }))
    bus.on('combat_ended', () => set({ combatActive: false }))
    bus.on('card_choice_required', (msg: any) => {
      const { type: _t, ...rest } = msg
      set({ pendingChoice: rest as PendingChoice })
    })
    bus.on('reaction_window_open', (msg: any) => {
      set({ reactionWindow: { ...msg, opened_at: Date.now() } })
    })
    bus.on('reaction_window_closed', () => set({ reactionWindow: null }))
  },

  disconnect() {
    bus.all.clear()
    disconnectSocket()
    set({
      gameCode: null, gameState: null, hand: [], myAddons: [],
      combatActive: false, pendingChoice: null, reactionWindow: null,
    })
  },

  send(action, data = {}) {
    sendAction(action, data)
  },

  clearPendingChoice() {
    set({ pendingChoice: null })
  },
}))
