import { create } from 'zustand'
import { bus, connectSocket, disconnectSocket, sendAction } from '../api/socket'
import type { GameState, HandCard, HandAddon } from '../types/game'

interface GameStore {
  gameCode: string | null
  myUserId: number | null
  gameState: GameState | null
  hand: HandCard[]
  myAddons: HandAddon[]
  combatActive: boolean
  connect: (gameCode: string, userId: number) => void
  disconnect: () => void
  send: (action: string, data?: Record<string, unknown>) => void
}

export const useGameStore = create<GameStore>((set) => ({
  gameCode: null,
  myUserId: null,
  gameState: null,
  hand: [],
  myAddons: [],
  combatActive: false,

  connect(gameCode, userId) {
    set({ gameCode, myUserId: userId })
    connectSocket(gameCode)

    bus.on('game_state', (msg: any) => set({ gameState: msg.game }))
    bus.on('hand_state', (msg: any) => {
      set({ hand: msg.hand ?? [], myAddons: msg.addons ?? [] })
    })
    bus.on('combat_started', () => set({ combatActive: true }))
    bus.on('combat_ended', () => set({ combatActive: false }))
  },

  disconnect() {
    bus.all.clear()
    disconnectSocket()
    set({ gameCode: null, gameState: null, hand: [], myAddons: [], combatActive: false })
  },

  send(action, data = {}) {
    sendAction(action, data)
  },
}))
