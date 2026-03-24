import { useEffect, useState, useCallback } from 'react'
import { useAuthStore } from '../store/authStore'
import { connectSocket, sendAction, disconnectSocket, bus } from '../api/socket'
import { api } from '../api/http'
import { CharacterSelect } from '../components/lobby/CharacterSelect'
import { PlayerList } from '../components/lobby/PlayerList'
import { Button } from '../components/ui/Button'
import type { PlayerState, GameState, Seniority, Role } from '../types/game'

interface Props {
  gameCode: string
  onGameStart: () => void
  onCancel: () => void
}

export function LobbyPage({ gameCode, onGameStart, onCancel }: Props) {
  const { user } = useAuthStore()
  const [players, setPlayers] = useState<PlayerState[]>([])
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [confirmed, setConfirmed] = useState(false)
  const [isHost, setIsHost] = useState(false)
  const [connected, setConnected] = useState(false)

  const myPlayer = players?.find((p) => p.user_id === user?.id)
  const allReady = players.length >= 2 && players.every((p) => p.seniority && p.role)

  const handleGameState = useCallback((msg: unknown) => {
    const state = (msg as { game: GameState }).game
    setPlayers(state.players ?? [])
    setMaxPlayers(state.max_players ?? 4)
    if (state.status === 'in_progress') onGameStart()
  }, [onGameStart])

  useEffect(() => {
    const ws = connectSocket(gameCode)
    ws.onopen = () => {
      setConnected(true)
      sendAction('join_game', { game_code: gameCode })
    }

    bus.on('game_state', handleGameState)
    bus.on('game_started', () => onGameStart())

    return () => {
      bus.off('game_state', handleGameState)
      bus.off('game_started', () => onGameStart())
      disconnectSocket()
    }
  }, [gameCode, handleGameState, onGameStart])

  useEffect(() => {
    if (players.length > 0 && user) {
      setIsHost(players[0]?.user_id === user.id)
    }
  }, [players, user])

  const handleConfirmCharacter = (seniority: Seniority, role: Role) => {
    sendAction('select_character', { seniority, role })
    setConfirmed(true)
  }

  const handleStartGame = () => {
    sendAction('start_game')
  }

  const handleCancel = async () => {
    await api.cancelGame(gameCode)
    disconnectSocket()
    onCancel()
  }

  if (!connected) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <p className="text-slate-400">Connessione in corso…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-violet-400">The Lost Trailbraizer</h1>
          <div className="flex items-center justify-center gap-2 mt-2">
            <span className="text-slate-500 text-sm">Codice partita:</span>
            <code className="bg-slate-800 text-violet-300 px-3 py-1 rounded-lg font-mono font-bold tracking-widest">
              {gameCode}
            </code>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Selezione personaggio */}
          <CharacterSelect
            onConfirm={handleConfirmCharacter}
            disabled={confirmed}
            confirmed={confirmed}
          />

          {/* Lista giocatori */}
          <div className="flex flex-col gap-4">
            <PlayerList
              players={players}
              maxPlayers={maxPlayers}
              currentUserId={user?.id ?? null}
            />

            {/* Abilità passiva del ruolo scelto */}
            {myPlayer?.role && (
              <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700 text-sm text-slate-400">
                <span className="text-violet-400 font-semibold">Abilità passiva:</span>{' '}
                seleziona un ruolo per vedere la tua abilità
              </div>
            )}

            {/* Avvia / Annulla partita (solo host) */}
            {isHost && (
              <div className="flex flex-col gap-2">
                <Button
                  onClick={handleStartGame}
                  disabled={!allReady}
                  className="w-full"
                  title={!allReady ? 'Tutti i giocatori devono scegliere il personaggio' : ''}
                >
                  {allReady ? 'Avvia partita' : `In attesa (${players.filter(p => p.seniority).length}/${players.length} pronti)`}
                </Button>
                {players.length === 1 && (
                  <button
                    onClick={handleCancel}
                    className="w-full text-sm text-slate-500 hover:text-red-400 border border-slate-700 hover:border-red-700 rounded-xl py-2 transition-colors"
                  >
                    Annulla partita
                  </button>
                )}
              </div>
            )}
            {!isHost && (
              <p className="text-center text-slate-600 text-sm">
                In attesa che l'host avvii la partita…
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
