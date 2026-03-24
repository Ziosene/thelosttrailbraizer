import type { GameState } from '../../types/game'

type DeckType = 'action' | 'addon' | 'boss'

interface DeckModalProps {
  type: DeckType
  gameState: GameState
  mustDraw: boolean
  onDrawDeck1: () => void
  onDrawDeck2: () => void
  onClose: () => void
}

const CONFIG: Record<DeckType, {
  label: string
  icon: string
  color: string
  headerBg: string
  deckBorder: string
  discardBorder: string
}> = {
  action: {
    label: 'Azioni',
    icon: '⚡',
    color: 'text-violet-300',
    headerBg: 'bg-violet-900/40 border-violet-700/50',
    deckBorder: 'border-violet-600/70',
    discardBorder: 'border-violet-800/50',
  },
  addon: {
    label: 'Addon',
    icon: '🔧',
    color: 'text-emerald-300',
    headerBg: 'bg-emerald-900/40 border-emerald-700/50',
    deckBorder: 'border-emerald-600/70',
    discardBorder: 'border-emerald-800/50',
  },
  boss: {
    label: 'Boss',
    icon: '👾',
    color: 'text-orange-300',
    headerBg: 'bg-orange-900/40 border-orange-700/50',
    deckBorder: 'border-orange-600/70',
    discardBorder: 'border-orange-800/50',
  },
}

function MiniDeck({
  label, count, accent, canDraw, onDraw,
}: {
  label: string
  count: number
  accent: string
  canDraw: boolean
  onDraw?: () => void
}) {
  const W = 80
  const H = Math.round(W * 1.45)
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className="text-slate-400 text-[10px] uppercase tracking-wider">{label}</span>
      <button
        onClick={canDraw ? onDraw : undefined}
        disabled={!canDraw || count === 0}
        style={{ width: W, height: H }}
        className="relative group shrink-0"
        title={canDraw ? `Pesca da ${label}` : undefined}
      >
        <div className={`absolute inset-0 rounded-xl border ${accent} bg-slate-800`}
          style={{ transform: 'rotate(-4deg) translate(2px, 2px)' }} />
        <div className={`absolute inset-0 rounded-xl border ${accent} bg-slate-800`}
          style={{ transform: 'rotate(-2deg) translate(1px, 1px)' }} />
        <div className={`absolute inset-0 rounded-xl border-2 ${accent} bg-slate-900 overflow-hidden flex flex-col
          ${canDraw && count > 0 ? 'group-hover:brightness-125 cursor-pointer' : 'opacity-50 cursor-default'} transition-all`}>
          <div className="px-1.5 pt-1.5 pb-0.5 text-[9px] font-bold text-slate-300 leading-tight truncate">{label}</div>
          <div className="flex-1 flex items-center justify-center text-3xl">🃏</div>
          <div className="px-1.5 py-1 text-[9px] font-bold text-slate-300 border-t border-slate-700/50">
            {count} <span className="text-slate-500 font-normal">carte</span>
          </div>
        </div>
      </button>
      {canDraw && count > 0 && (
        <span className="text-[9px] text-violet-400 font-semibold animate-pulse">↑ Pesca</span>
      )}
    </div>
  )
}

function DiscardPile({
  label, count, topName, topSub, accent,
}: {
  label: string
  count: number
  topName?: string
  topSub?: string
  accent: string
}) {
  const W = 80
  const H = Math.round(W * 1.45)
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className="text-slate-400 text-[10px] uppercase tracking-wider">{label}</span>
      <div
        style={{ width: W, height: H }}
        className={`rounded-xl border-2 ${accent} bg-slate-900/60 overflow-hidden flex flex-col`}
      >
        {topName ? (
          <>
            <div className="px-1.5 pt-1.5 pb-0.5 text-[9px] font-bold text-slate-300 leading-tight truncate">{topName}</div>
            <div className="flex-1 flex items-center justify-center text-3xl opacity-40">🃏</div>
            {topSub && (
              <div className="px-1.5 py-0.5 text-[8px] text-slate-500 border-t border-slate-700/50 truncate">{topSub}</div>
            )}
            <div className="px-1.5 py-1 text-[9px] text-slate-400 border-t border-slate-700/50">
              {count} <span className="text-slate-600 font-normal">tot.</span>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-1 text-slate-700">
            <span className="text-2xl">∅</span>
            <span className="text-[9px]">vuoto</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function DeckModal({ type, gameState: gs, mustDraw, onDrawDeck1, onDrawDeck2, onClose }: DeckModalProps) {
  const cfg = CONFIG[type]

  const deck1Count = type === 'action' ? gs.action_deck_1_count
    : type === 'addon' ? gs.addon_deck_1_count
    : gs.boss_deck_1_count

  const deck2Count = type === 'action' ? gs.action_deck_2_count
    : type === 'addon' ? gs.addon_deck_2_count
    : gs.boss_deck_2_count

  const discardCount = type === 'action' ? gs.action_discard_count
    : type === 'addon' ? gs.addon_graveyard_count
    : gs.boss_graveyard_count

  const discardTop = type === 'action' ? gs.action_discard_top
    : type === 'addon' ? gs.addon_graveyard_top
    : gs.boss_graveyard_top

  const discardTopName = discardTop?.name
  const _dt = discardTop as unknown as Record<string, string> | undefined
  const discardTopSub: string | undefined = _dt
    ? (_dt['card_type'] ?? _dt['difficulty'] ?? _dt['rarity'])
    : undefined

  const canDraw = mustDraw && type === 'action'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="bg-slate-950 border border-slate-700 rounded-2xl shadow-2xl p-5 flex flex-col gap-4 min-w-[320px]"
      >
        {/* Header */}
        <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${cfg.headerBg}`}>
          <span className="text-xl">{cfg.icon}</span>
          <span className={`font-bold text-sm ${cfg.color}`}>Mazzi {cfg.label}</span>
          <button
            onClick={onClose}
            className="ml-auto text-slate-500 hover:text-slate-300 text-lg leading-none transition-colors"
          >
            ×
          </button>
        </div>

        {/* Mazzi + scarti */}
        <div className="flex items-start gap-6 justify-center">
          <MiniDeck
            label="Mazzo 1"
            count={deck1Count}
            accent={cfg.deckBorder}
            canDraw={canDraw}
            onDraw={onDrawDeck1}
          />
          <MiniDeck
            label="Mazzo 2"
            count={deck2Count}
            accent={cfg.deckBorder}
            canDraw={canDraw}
            onDraw={onDrawDeck2}
          />

          <div className="w-px bg-slate-800 self-stretch" />

          <DiscardPile
            label="Scarti"
            count={discardCount}
            topName={discardTopName}
            topSub={discardTopSub}
            accent={cfg.discardBorder}
          />
        </div>

        {canDraw && (
          <p className="text-center text-amber-400 text-[11px] font-semibold animate-pulse">
            È il tuo turno — pesca da uno dei mazzi
          </p>
        )}
      </div>
    </div>
  )
}
