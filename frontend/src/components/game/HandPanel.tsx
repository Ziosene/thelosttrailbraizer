import type { HandCard } from '../../types/game'
import type { GameState } from '../../types/game'
import { CardVisual, DeckCard } from './CardVisual'
import type { CardInfo } from './CardVisual'

interface HandPanelProps {
  hand: HandCard[]
  gameState: GameState
  onCardClick: (c: CardInfo) => void
  onPlayCard: (handCardId: number) => void
  onDrawCard: (deck: 1 | 2) => void
}

export function HandPanel({ hand, gameState, onCardClick, onPlayCard, onDrawCard }: HandPanelProps) {
  return (
    <div className="bg-slate-900/90 border-t border-slate-800 px-4 pt-3 pb-2 shrink-0 flex gap-4 min-h-0">
      {/* Carte mano */}
      <div className="flex flex-col flex-1 min-w-0">
        <div className="text-slate-600 text-xs uppercase tracking-wider mb-2">
          La tua mano ({hand.length})
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
                actionLabel="Gioca"
                width={90}
                onClick={() => onCardClick({
                  type: 'action', name: c.name,
                  subtitle: `#${c.card_id} · ${c.card_type}`,
                  effect: c.effect,
                  actionLabel: 'Gioca',
                  onAction: () => onPlayCard(c.hand_card_id),
                })}
                onAction={() => onPlayCard(c.hand_card_id)}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="w-px bg-slate-800 self-stretch shrink-0" />

      {/* Mazzi */}
      <div className="shrink-0 flex items-center gap-3">
        <div className="flex flex-col items-center gap-1">
          <span className="text-slate-500 text-[9px] uppercase tracking-wider">Azioni</span>
          <div className="flex gap-1.5">
            <DeckCard icon="⚡" label="Mazzo 1" count={gameState.action_deck_1_count} accent="border-violet-600/70"
              onDraw={() => onDrawCard(1)} />
            <DeckCard icon="⚡" label="Mazzo 2" count={gameState.action_deck_2_count} accent="border-blue-600/70"
              onDraw={() => onDrawCard(2)} />
          </div>
        </div>
        <div className="w-px bg-slate-800 self-stretch" />
        <div className="flex flex-col items-center gap-1">
          <span className="text-slate-500 text-[9px] uppercase tracking-wider">Addon</span>
          <div className="flex gap-1.5">
            <DeckCard icon="🔧" label="Mazzo 1" count={gameState.addon_deck_1_count} accent="border-emerald-600/70" />
            <DeckCard icon="🔧" label="Mazzo 2" count={gameState.addon_deck_2_count} accent="border-teal-600/70" />
          </div>
        </div>
        <div className="w-px bg-slate-800 self-stretch" />
        <div className="flex flex-col items-center gap-1">
          <span className="text-slate-500 text-[9px] uppercase tracking-wider">Boss</span>
          <div className="flex gap-1.5">
            <DeckCard icon="👾" label="Mazzo 1" count={gameState.boss_deck_1_count} accent="border-orange-600/70" />
            <DeckCard icon="👾" label="Mazzo 2" count={gameState.boss_deck_2_count} accent="border-red-600/70" />
          </div>
        </div>
      </div>
    </div>
  )
}
