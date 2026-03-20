import type { PlayerState } from '../../types/game'

interface Props {
  players: PlayerState[]
  maxPlayers: number
  currentUserId: number | null
}

export function PlayerList({ players, maxPlayers, currentUserId }: Props) {
  const slots = Array.from({ length: maxPlayers })

  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
      <h2 className="text-lg font-bold text-slate-100 mb-4">
        Giocatori {players.length}/{maxPlayers}
      </h2>
      <div className="flex flex-col gap-3">
        {slots.map((_, i) => {
          const player = players[i]
          if (!player) {
            return (
              <div key={i} className="flex items-center gap-3 py-3 px-4 rounded-lg border border-dashed border-slate-700 text-slate-600 text-sm">
                In attesa…
              </div>
            )
          }
          const isMe = player.user_id === currentUserId
          const ready = !!player.seniority && !!player.role
          return (
            <div
              key={player.id}
              className={`flex items-center gap-3 py-3 px-4 rounded-lg border ${isMe ? 'border-violet-500 bg-violet-950/30' : 'border-slate-700'}`}
            >
              <div className="flex-1">
                <div className="font-semibold text-slate-100">
                  {player.nickname}
                  {isMe && <span className="ml-2 text-xs text-violet-400">(tu)</span>}
                </div>
                {ready ? (
                  <div className="text-xs text-slate-400 mt-0.5">
                    {player.seniority} · {player.role}
                  </div>
                ) : (
                  <div className="text-xs text-slate-600 mt-0.5">Scelta personaggio…</div>
                )}
              </div>
              <div className={`w-2.5 h-2.5 rounded-full ${ready ? 'bg-green-500' : 'bg-slate-600'}`} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
