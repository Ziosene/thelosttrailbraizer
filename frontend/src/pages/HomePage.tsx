import { useState, useEffect } from 'react'
import { api, type GameInfoDTO } from '../api/http'
import { useAuthStore } from '../store/authStore'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

interface Props {
  onJoinGame: (code: string) => void
}

export function HomePage({ onJoinGame }: Props) {
  const { user } = useAuthStore()
  const [games, setGames] = useState<GameInfoDTO[]>([])
  const [myGames, setMyGames] = useState<GameInfoDTO[]>([])
  const [codeInput, setCodeInput] = useState('')
  const [maxPlayers, setMaxPlayers] = useState(4)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.listGames().then(setGames).catch(() => {})
    api.listMyGames().then(setMyGames).catch(() => {})
  }, [])

  const handleCreate = async () => {
    setLoading(true)
    setError('')
    try {
      const game = await api.createGame(maxPlayers)
      onJoinGame(game.code)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Errore creazione partita')
    } finally {
      setLoading(false)
    }
  }

  const handleJoinByCode = () => {
    const code = codeInput.trim().toUpperCase()
    if (code.length >= 4) onJoinGame(code)
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-violet-400 mb-1">The Lost Trailbraizer</h1>
          <p className="text-slate-500 text-sm">Benvenuto, <span className="text-slate-300">{user?.nickname}</span></p>
        </div>

        {/* Crea partita */}
        <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-4">
          <h2 className="text-lg font-bold text-slate-100 mb-4">Crea una nuova partita</h2>
          <div className="mb-4">
            <p className="text-sm text-slate-400 mb-2">Numero di giocatori</p>
            <div className="flex gap-2">
              {[2, 3, 4].map((n) => (
                <button
                  key={n}
                  onClick={() => setMaxPlayers(n)}
                  className={`flex-1 py-2 rounded-lg font-semibold border transition-all ${
                    maxPlayers === n
                      ? 'bg-violet-600 border-violet-500 text-white'
                      : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-violet-500'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
          <Button onClick={handleCreate} loading={loading} className="w-full">
            Crea partita
          </Button>
        </div>

        {/* Unisciti con codice */}
        <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-4">
          <h2 className="text-lg font-bold text-slate-100 mb-4">Unisciti con codice</h2>
          <div className="flex gap-2">
            <Input
              placeholder="ABCD1234"
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
              className="flex-1 font-mono tracking-widest"
              maxLength={8}
            />
            <Button onClick={handleJoinByCode} disabled={codeInput.trim().length < 4} variant="secondary">
              Entra
            </Button>
          </div>
        </div>

        {/* Le mie partite */}
        {myGames.length > 0 && (
          <div className="bg-slate-900 rounded-2xl p-6 border border-violet-800/50 mb-4">
            <h2 className="text-lg font-bold text-violet-300 mb-4">▶ Le mie partite</h2>
            <div className="flex flex-col gap-2">
              {myGames.map((g) => (
                <div key={g.id} className="flex items-center justify-between py-2 px-3 bg-slate-800 rounded-lg">
                  <div>
                    <code className="text-violet-300 font-mono font-bold">{g.code}</code>
                    <span className="text-slate-500 text-sm ml-3">{g.player_count}/{g.max_players} giocatori</span>
                    <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${g.status === 'waiting' ? 'bg-amber-900/50 text-amber-400' : 'bg-green-900/50 text-green-400'}`}>
                      {g.status === 'waiting' ? 'In attesa' : 'In corso'}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {g.status === 'waiting' && g.player_count === 1 && (
                      <button
                        onClick={async () => {
                          await api.cancelGame(g.code)
                          setMyGames(prev => prev.filter(x => x.code !== g.code))
                        }}
                        className="text-xs text-slate-500 hover:text-red-400 border border-slate-700 hover:border-red-700 rounded px-2 py-1 transition-colors"
                      >
                        Annulla
                      </button>
                    )}
                    <Button variant="secondary" onClick={() => onJoinGame(g.code)} className="text-sm py-1 px-3">
                      {g.status === 'waiting' ? 'Entra' : 'Riprendi'}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Partite aperte */}
        {games.length > 0 && (
          <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-4">
            <h2 className="text-lg font-bold text-slate-100 mb-4">Partite aperte</h2>
            <div className="flex flex-col gap-2">
              {games.map((g) => (
                <div key={g.id} className="flex items-center justify-between py-2 px-3 bg-slate-800 rounded-lg">
                  <div>
                    <code className="text-violet-300 font-mono font-bold">{g.code}</code>
                    <span className="text-slate-500 text-sm ml-3">{g.player_count}/{g.max_players} giocatori</span>
                  </div>
                  <Button variant="secondary" onClick={() => onJoinGame(g.code)} className="text-sm py-1 px-3">
                    Entra
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
