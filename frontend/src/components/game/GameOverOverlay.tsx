import type { PlayerState } from '../../types/game'

interface GameOverOverlayProps {
  winnerId: number
  players: PlayerState[]
  onGoHome: () => void
}

export function GameOverOverlay({ winnerId, players, onGoHome }: GameOverOverlayProps) {
  const winner = players.find(p => p.id === winnerId)
  const sorted = [...players].sort((a, b) => {
    if (a.id === winnerId) return -1
    if (b.id === winnerId) return 1
    return b.certificazioni - a.certificazioni || b.licenze - a.licenze
  })

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="bg-slate-950 border border-yellow-600/40 rounded-2xl shadow-2xl p-8 flex flex-col items-center gap-6 min-w-[360px] max-w-lg w-full mx-4">

        {/* Trophy */}
        <div className="text-6xl">🏆</div>

        <div className="text-center">
          <div className="text-yellow-400 font-bold text-2xl mb-1">Partita finita!</div>
          {winner && (
            <div className="text-white text-lg">
              Vince <span className="text-yellow-300 font-bold">{winner.nickname}</span>
              {winner.role && (
                <span className="block text-slate-400 text-sm mt-0.5">{winner.role}</span>
              )}
            </div>
          )}
        </div>

        {/* Leaderboard */}
        <div className="w-full">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs uppercase border-b border-slate-800">
                <th className="text-left pb-2 font-normal">Giocatore</th>
                <th className="text-right pb-2 font-normal">HP</th>
                <th className="text-right pb-2 font-normal">Licenze</th>
                <th className="text-right pb-2 font-normal">Cert.</th>
                <th className="text-right pb-2 font-normal">Boss</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(p => {
                const isWinner = p.id === winnerId
                return (
                  <tr
                    key={p.id}
                    className={`border-b border-slate-800/50 ${isWinner ? 'text-yellow-300' : 'text-slate-300'}`}
                  >
                    <td className="py-2">
                      {isWinner && <span className="mr-1">🥇</span>}
                      <span className="font-semibold">{p.nickname}</span>
                      {p.role && (
                        <span className="block text-slate-500 text-[10px]">{p.role}</span>
                      )}
                    </td>
                    <td className="text-right py-2">
                      <span className={p.hp <= 0 ? 'text-red-500' : ''}>{p.hp}</span>
                      <span className="text-slate-600">/{p.max_hp}</span>
                    </td>
                    <td className="text-right py-2">{p.licenze}</td>
                    <td className="text-right py-2">{p.certificazioni}</td>
                    <td className="text-right py-2">{p.bosses_defeated}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <button
          onClick={onGoHome}
          className="mt-2 px-6 py-2.5 bg-violet-700 hover:bg-violet-600 text-white font-semibold rounded-xl transition-colors"
        >
          Torna alla home
        </button>
      </div>
    </div>
  )
}
