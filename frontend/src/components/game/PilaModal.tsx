import { useState, useEffect } from 'react'
import type { PilaState, PilaStackItem } from '../../store/gameStore'
import type { HandCard } from '../../types/game'

interface PilaModalProps {
  pila: PilaState
  myPlayerId: number | null
  hand: HandCard[]
  onPass: () => void
  onPlayCard: (handCardId: number) => void
}

export function PilaModal({ pila, myPlayerId, hand, onPass, onPlayCard }: PilaModalProps) {
  const iMyTurn = pila.priority_player_id === myPlayerId
  const [timeLeft, setTimeLeft] = useState(Math.ceil(pila.timeout_ms / 1000))

  useEffect(() => {
    setTimeLeft(Math.ceil(pila.timeout_ms / 1000))
    const interval = setInterval(() => {
      setTimeLeft(prev => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(interval)
  }, [pila.priority_player_id, pila.opened_at, pila.timeout_ms])

  // Only show cards that can be played out-of-turn (Lucky Roll card 27, difensiva type)
  const playableCards = hand.filter(c =>
    c.card_type === 'Difensiva' || c.name?.toLowerCase().includes('lucky roll')
  )

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center pb-4 pointer-events-none">
      <div
        className="bg-slate-950 border border-violet-700/60 rounded-2xl shadow-2xl p-4 w-full max-w-lg pointer-events-auto"
        style={{ maxHeight: '40vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-violet-400 font-bold text-sm">🃏 La Pila</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${timeLeft <= 3 ? 'bg-red-800/60 text-red-300 animate-pulse' : 'bg-slate-800 text-slate-400'}`}>
            {timeLeft}s
          </span>
          {iMyTurn && (
            <span className="ml-auto text-violet-300 text-xs font-semibold animate-pulse">← Tocca a te!</span>
          )}
        </div>

        {/* Stack items */}
        <div className="flex flex-col-reverse gap-1 mb-3">
          {pila.stack.map((item, i) => (
            <StackItemRow key={i} item={item} isTop={i === pila.stack.length - 1} />
          ))}
        </div>

        {/* Actions */}
        {iMyTurn && (
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={onPass}
              className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300 text-xs font-semibold transition-colors"
            >
              Passa →
            </button>
            {playableCards.map(c => (
              <button
                key={c.hand_card_id}
                onClick={() => onPlayCard(c.hand_card_id)}
                className="px-3 py-1.5 rounded-lg bg-violet-900/60 hover:bg-violet-800/80 border border-violet-600/60 text-violet-200 text-xs font-semibold transition-colors"
                title={c.effect}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}
        {!iMyTurn && (
          <div className="text-center text-slate-500 text-xs italic">
            In attesa del giocatore #{pila.priority_player_id}...
          </div>
        )}
      </div>
    </div>
  )
}

function StackItemRow({ item, isTop }: { item: PilaStackItem; isTop: boolean }) {
  if (item.kind === 'dice_result') {
    const hit = item.result === 'hit'
    return (
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs border ${
        hit ? 'bg-green-950/40 border-green-800/50 text-green-300' : 'bg-red-950/40 border-red-800/50 text-red-300'
      }`}>
        <span className="text-lg">🎲</span>
        <span className="font-bold">{item.roll}</span>
        <span className="text-slate-500">soglia {item.threshold}</span>
        <span className={`ml-auto font-semibold ${hit ? 'text-green-400' : 'text-red-400'}`}>
          {hit ? 'COLPITO' : 'mancato'}
        </span>
        <span className="text-[9px] text-slate-600 ml-1">[base]</span>
      </div>
    )
  }
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs border ${
      isTop ? 'bg-violet-950/40 border-violet-700/60 text-violet-300' : 'bg-slate-900 border-slate-700 text-slate-400'
    }`}>
      <span>🃏</span>
      <span className="font-semibold">{item.card_name}</span>
      {item.force_reroll && <span className="text-amber-400 text-[10px]">↻ reroll</span>}
      {item.roll_modifier !== 0 && (
        <span className={item.roll_modifier! > 0 ? 'text-green-400' : 'text-red-400'}>
          {item.roll_modifier! > 0 ? '+' : ''}{item.roll_modifier}
        </span>
      )}
      <span className="ml-auto text-[9px] text-slate-600">giocatore #{item.played_by}</span>
    </div>
  )
}
