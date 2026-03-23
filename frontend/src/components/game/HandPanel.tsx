import { useState } from 'react'
import type { HandCard } from '../../types/game'
import type { GameState } from '../../types/game'
import { CardVisual } from './CardVisual'
import type { CardInfo } from './CardVisual'
import { DeckModal } from './DeckModal'

type DeckType = 'action' | 'addon' | 'boss'

interface HandPanelProps {
  hand: HandCard[]
  gameState: GameState
  isMyTurn: boolean
  onCardClick: (c: CardInfo) => void
  onPlayCard: (handCardId: number) => void
  onDrawCard: (deck: 1 | 2) => void
}

export function HandPanel({ hand, gameState, isMyTurn, onCardClick, onPlayCard, onDrawCard }: HandPanelProps) {
  const [openDeck, setOpenDeck] = useState<DeckType | null>(null)
  const phase = gameState.current_phase
  const canPlay = isMyTurn && (phase === 'action' || phase === 'combat')
  const mustDraw = isMyTurn && phase === 'draw'

  return (
    <div className="bg-slate-900/90 border-t border-slate-800 px-4 pt-3 pb-2 shrink-0 flex gap-4 min-h-0">
      {/* Carte mano */}
      <div className="flex flex-col flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-slate-600 text-xs uppercase tracking-wider">
            La tua mano ({hand.length})
          </span>
          {mustDraw && (
            <span className="text-amber-400 text-[10px] font-semibold animate-pulse">
              ← pesca prima di giocare
            </span>
          )}
          {!isMyTurn && (
            <span className="text-slate-600 text-[10px] italic">non è il tuo turno</span>
          )}
        </div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {hand.length === 0 && (
            <span className="text-slate-700 text-xs italic">Nessuna carta in mano</span>
          )}
          {hand.map((c) => (
            <div key={c.hand_card_id} className="shrink-0">
              <CardVisual
                type="action"
                name={c.name}
                subtitle={`#${c.card_id} · ${c.card_type}`}
                actionLabel={canPlay ? 'Gioca' : undefined}
                width={90}
                onClick={() => onCardClick({
                  type: 'action', name: c.name,
                  subtitle: `#${c.card_id} · ${c.card_type}`,
                  effect: c.effect,
                  actionLabel: canPlay ? 'Gioca' : undefined,
                  onAction: canPlay ? () => onPlayCard(c.hand_card_id) : undefined,
                })}
                onAction={canPlay ? () => onPlayCard(c.hand_card_id) : undefined}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="w-px bg-slate-800 self-stretch shrink-0" />

      {/* 3 pulsanti mazzi */}
      <div className="shrink-0 flex flex-col justify-center gap-2">
        <DeckButton
          icon="⚡"
          label="Azioni"
          count={gameState.action_deck_1_count + gameState.action_deck_2_count}
          highlight={mustDraw}
          color="violet"
          onClick={() => setOpenDeck('action')}
        />
        <DeckButton
          icon="🔧"
          label="Addon"
          count={gameState.addon_deck_1_count + gameState.addon_deck_2_count}
          highlight={false}
          color="emerald"
          onClick={() => setOpenDeck('addon')}
        />
        <DeckButton
          icon="👾"
          label="Boss"
          count={gameState.boss_deck_1_count + gameState.boss_deck_2_count}
          highlight={false}
          color="orange"
          onClick={() => setOpenDeck('boss')}
        />
      </div>

      {/* Modale mazzi */}
      {openDeck && (
        <DeckModal
          type={openDeck}
          gameState={gameState}
          mustDraw={mustDraw}
          onDrawDeck1={() => { onDrawCard(1); setOpenDeck(null) }}
          onDrawDeck2={() => { onDrawCard(2); setOpenDeck(null) }}
          onClose={() => setOpenDeck(null)}
        />
      )}
    </div>
  )
}

function DeckButton({ icon, label, count, highlight, color, onClick }: {
  icon: string
  label: string
  count: number
  highlight: boolean
  color: 'violet' | 'emerald' | 'orange'
  onClick: () => void
}) {
  const colorMap = {
    violet:  'border-violet-700/60 hover:border-violet-500 text-violet-300',
    emerald: 'border-emerald-700/60 hover:border-emerald-500 text-emerald-300',
    orange:  'border-orange-700/60 hover:border-orange-500 text-orange-300',
  }
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border bg-slate-800/80 hover:bg-slate-700/80
        transition-colors text-xs font-semibold
        ${colorMap[color]}
        ${highlight ? 'ring-2 ring-amber-400/60 animate-pulse' : ''}`}
    >
      <span>{icon}</span>
      <span>{label}</span>
      <span className="ml-auto text-slate-500 font-normal text-[10px]">{count}</span>
    </button>
  )
}
