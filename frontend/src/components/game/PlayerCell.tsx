import type { PlayerState, PublicAddon } from '../../types/game'
import { CardVisual } from './CardVisual'
import type { CardInfo } from './CardVisual'

export type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'bottom-full' | 'top-full'

// ─── Atomi ────────────────────────────────────────────────────────────────────

function HP({ cur, max }: { cur: number; max: number }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {Array.from({ length: max }).map((_, i) => (
        <div key={i} className={`w-3 h-3 rounded-full border ${i < cur ? 'bg-red-400 border-red-500' : 'bg-slate-700 border-slate-600'}`} />
      ))}
    </div>
  )
}

function Certs({ count }: { count: number }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className={`w-2.5 h-2.5 rounded-sm ${i < count ? 'bg-violet-400' : 'bg-slate-700'}`} />
      ))}
    </div>
  )
}

// ─── PlayerCell ───────────────────────────────────────────────────────────────

interface PlayerCellProps {
  p: PlayerState
  isMe?: boolean
  corner: Corner
  onCardClick: (c: CardInfo) => void
  onEndTurn?: () => void
}

export function PlayerCell({ p, isMe, corner, onCardClick, onEndTurn }: PlayerCellProps) {
  const isRight = corner === 'top-right' || corner === 'bottom-right'
  const bg = isMe ? 'bg-violet-950/25' : 'bg-slate-900/40'
  const floatSide: 'left' | 'right' = isRight ? 'left' : 'right'

  return (
    <div className={`flex-1 ${bg} p-2`}>
      {/* Info card floated */}
      <div
        style={{ float: floatSide, margin: '4px 6px 6px 4px' }}
        className={`flex flex-col gap-1 p-2 rounded-xl
          ${isMe ? 'bg-violet-900/30 border border-violet-700/40' : 'bg-slate-800/60 border border-slate-700/40'}`}
      >
        <div className={`font-bold text-xs ${isMe ? 'text-violet-300' : 'text-slate-200'}`}>{p.nickname}</div>
        <div className="text-slate-500 text-[10px] leading-tight max-w-[130px] truncate">
          {p.seniority ?? '?'} · {p.role}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <HP cur={p.hp} max={p.max_hp} />
          <span className="text-yellow-400 text-[10px] font-semibold">💰{p.licenze}L</span>
        </div>
        <Certs count={p.certificazioni} />
        <div className="text-slate-400 text-[10px]">🃏 {p.hand_count} in mano</div>
        {p.is_in_combat && (
          <span className="text-red-400 text-[10px] font-semibold">⚔️ In combattimento</span>
        )}
        {isMe && (
          <button
            onClick={onEndTurn}
            className="mt-1 bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg py-1 px-3 text-xs font-semibold transition-colors"
          >
            Fine turno
          </button>
        )}
      </div>

      {/* Addon del giocatore */}
      <div className={isRight ? 'text-right' : 'text-left'}>
        {p.addons.length === 0 && (
          <span className="text-slate-700 text-[10px] italic">nessun addon</span>
        )}
        {p.addons.map((a: PublicAddon) => (
          <div
            key={a.player_addon_id}
            style={{ display: 'inline-block', margin: '3px', verticalAlign: 'top' }}
            className={a.is_tapped ? 'opacity-35 grayscale' : ''}
          >
            <CardVisual
              type="addon"
              name={a.name}
              width={70}
              onClick={() => onCardClick({ type: 'addon', name: a.name, effect: a.effect })}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
