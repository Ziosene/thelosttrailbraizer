import type { HandCard } from '../../types/game'

// ─── Tipo CardInfo ─────────────────────────────────────────────────────────────

export type CardInfo = {
  name: string
  type: 'boss' | 'addon' | 'action'
  subtitle?: string
  statLeft?: string
  statRight?: string
  reward?: string
  effect?: string
  actionLabel?: string
  onAction?: () => void
}

// ─── Stili per tipo ────────────────────────────────────────────────────────────

export const CARD_BORDER: Record<string, string> = {
  boss:   'border-amber-800/80 hover:border-amber-500',
  addon:  'border-violet-800/70 hover:border-violet-500',
  action: 'border-slate-700 hover:border-slate-500',
}
const CARD_HEADER: Record<string, string> = {
  boss:   'bg-stone-900 text-amber-200',
  addon:  'bg-slate-900 text-violet-200',
  action: 'bg-slate-900 text-slate-200',
}
const CARD_ART_BG: Record<string, string> = {
  boss:   'bg-gradient-to-b from-red-950/60 to-stone-900/80',
  addon:  'bg-gradient-to-b from-violet-950/60 to-slate-900/80',
  action: 'bg-gradient-to-b from-slate-800/60 to-slate-900/80',
}

// ─── CardVisual ───────────────────────────────────────────────────────────────

interface CardVisualProps {
  name: string
  subtitle?: string
  statLeft?: string
  statRight?: string
  reward?: string
  type: 'boss' | 'addon' | 'action'
  onClick?: () => void
  actionLabel?: string
  onAction?: () => void
  width?: number
}

export function CardVisual({
  name, subtitle, statLeft, statRight, reward, type,
  onClick, actionLabel, onAction, width = 110,
}: CardVisualProps) {
  const aspectH = Math.round(width * 1.45)
  return (
    <div
      onClick={onClick}
      style={{ width, minWidth: width, height: aspectH }}
      className={`relative flex flex-col rounded-xl border-2 overflow-hidden cursor-pointer transition-all duration-150 hover:scale-105 shadow-lg
        ${CARD_BORDER[type]} bg-stone-950`}
    >
      <div className={`px-2 py-1 text-center text-[10px] font-bold leading-tight ${CARD_HEADER[type]}`}>
        {name}
      </div>
      <div className={`flex-1 flex items-center justify-center ${CARD_ART_BG[type]}`}>
        <span className="text-3xl opacity-30">
          {type === 'boss' ? '👾' : type === 'addon' ? '🔧' : '🃏'}
        </span>
      </div>
      {(statLeft || statRight) && (
        <div className="bg-stone-900/90 px-2 py-1 flex justify-between items-center">
          {statLeft  && <span className="text-[10px] text-red-300 font-bold">❤️ {statLeft}</span>}
          {statRight && <span className="text-[10px] text-slate-300 font-bold">🎲 {statRight}+</span>}
        </div>
      )}
      {subtitle && (
        <div className="bg-stone-950/90 px-2 py-0.5 text-center text-[9px] text-slate-400 leading-tight">
          {subtitle}
        </div>
      )}
      {reward && (
        <div className="bg-stone-900 px-2 py-0.5 text-center text-[9px] text-amber-300 font-semibold">
          {reward}
        </div>
      )}
      {actionLabel && (
        <button
          onClick={e => { e.stopPropagation(); onAction?.() }}
          className="bg-slate-800/90 hover:bg-slate-700 text-[10px] font-semibold text-slate-200 py-1 transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

// ─── CardOverlay ──────────────────────────────────────────────────────────────

export function CardOverlay({ card, onClose }: { card: CardInfo; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-6"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="flex flex-col items-center gap-3 max-w-xs w-full"
      >
        <CardVisual
          type={card.type}
          name={card.name}
          subtitle={card.subtitle}
          statLeft={card.statLeft}
          statRight={card.statRight}
          reward={card.reward}
          width={260}
        />
        {card.effect && (
          <div className="w-full bg-slate-900/95 border border-slate-700 rounded-xl px-4 py-3 text-slate-300 text-sm leading-relaxed">
            {card.effect}
          </div>
        )}
        {card.actionLabel && card.onAction && (
          <button
            onClick={() => { card.onAction!(); onClose() }}
            className="w-full bg-violet-700 hover:bg-violet-600 border border-violet-500 rounded-xl py-2.5
              text-white font-semibold text-sm transition-colors"
          >
            {card.actionLabel}
          </button>
        )}
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 text-xs transition-colors"
        >
          Chiudi
        </button>
      </div>
    </div>
  )
}

// ─── DeckCard ─────────────────────────────────────────────────────────────────

export function DeckCard({ icon, label, count, accent, onDraw }: {
  icon: string; label: string; count: number; accent: string; onDraw?: () => void
}) {
  const W = 62
  const H = Math.round(W * 1.45)
  return (
    <button
      title={`Pesca da ${label}`}
      onClick={onDraw}
      className="relative group shrink-0 flex-none"
      style={{ width: W, height: H }}
    >
      <div className={`absolute inset-0 rounded-xl border ${accent} bg-slate-800`}
        style={{ transform: 'rotate(-4deg) translate(2px, 2px)' }} />
      <div className={`absolute inset-0 rounded-xl border ${accent} bg-slate-800`}
        style={{ transform: 'rotate(-2deg) translate(1px, 1px)' }} />
      <div className={`absolute inset-0 rounded-xl border-2 ${accent} bg-slate-900 overflow-hidden flex flex-col group-hover:brightness-125 transition-all`}>
        <div className="px-1.5 pt-1.5 pb-0.5 text-[8px] font-bold text-slate-300 leading-tight truncate">{label}</div>
        <div className="flex-1 flex items-center justify-center text-2xl">{icon}</div>
        <div className="px-1.5 py-1 text-[8px] font-bold text-slate-300 border-t border-slate-700/50">
          {count} <span className="text-slate-600 font-normal">carte</span>
        </div>
      </div>
    </button>
  )
}

// ─── HandCardVisual (alias per le carte in mano, width fisso) ─────────────────

export function HandCardVisual({ c, onOpen, onPlay }: {
  c: HandCard
  onOpen: () => void
  onPlay: () => void
}) {
  return (
    <div className="shrink-0">
      <CardVisual
        type="action"
        name={c.name}
        subtitle={`#${c.card_id} · ${c.card_type}`}
        actionLabel="Gioca"
        width={90}
        onClick={onOpen}
        onAction={onPlay}
      />
    </div>
  )
}
