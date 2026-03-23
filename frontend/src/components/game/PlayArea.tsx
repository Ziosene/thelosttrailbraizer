import type { PlayerState, AddonMarketInfo, BossMarketInfo } from '../../types/game'
import { CardVisual } from './CardVisual'
import type { CardInfo } from './CardVisual'
import { PlayerCell } from './PlayerCell'
import type { Corner } from './PlayerCell'

const SIDEBAR_W = 'w-48'
const SIDEBAR_CARD_W = 152

// ─── LeftSidebar ──────────────────────────────────────────────────────────────

interface LeftSidebarProps {
  addonMarket1: AddonMarketInfo | null
  addonMarket2: AddonMarketInfo | null
  onCardClick: (c: CardInfo) => void
  onBuyAddon: (slot: 1 | 2) => void
}

function LeftSidebar({ addonMarket1, addonMarket2, onCardClick, onBuyAddon }: LeftSidebarProps) {
  const addonSlots = [
    { slot: 1 as const, info: addonMarket1 },
    { slot: 2 as const, info: addonMarket2 },
  ]

  return (
    <div className={`${SIDEBAR_W} shrink-0 border-r border-slate-800 bg-slate-900/60 flex flex-col gap-4 p-3 overflow-y-auto min-h-0 self-stretch`}>
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Addon mercato</div>
        <div className="flex flex-col gap-2">
          {addonSlots.map(({ slot, info }) =>
            info ? (
              <CardVisual
                key={slot}
                type="addon"
                name={info.name}
                subtitle={`${info.cost}L · ${info.rarity}`}
                actionLabel="+ Acquista"
                width={SIDEBAR_CARD_W}
                onClick={() => onCardClick({
                  type: 'addon', name: info.name, subtitle: `${info.cost}L · ${info.rarity}`,
                  effect: info.effect, actionLabel: '+ Acquista', onAction: () => onBuyAddon(slot),
                })}
                onAction={() => onBuyAddon(slot)}
              />
            ) : (
              <div key={slot} className="rounded-xl border border-slate-800/50 bg-slate-900/30 flex items-center justify-center text-slate-700 text-[10px] italic"
                style={{ height: Math.round(SIDEBAR_CARD_W * 1.45) }}>
                slot vuoto
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

// ─── BossSidebar ──────────────────────────────────────────────────────────────

interface BossSidebarProps {
  bossMarket1: BossMarketInfo | null
  bossMarket2: BossMarketInfo | null
  onCardClick: (c: CardInfo) => void
  onStartCombat: (slot: 1 | 2) => void
}

function BossSidebar({ bossMarket1, bossMarket2, onCardClick, onStartCombat }: BossSidebarProps) {
  const bossSlots = [
    { slot: 1 as const, info: bossMarket1 },
    { slot: 2 as const, info: bossMarket2 },
  ]

  return (
    <div className={`${SIDEBAR_W} shrink-0 border-l border-slate-800 bg-slate-900/60 flex flex-col gap-4 p-3 overflow-y-auto min-h-0 self-stretch`}>
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Boss attivi</div>
        <div className="flex flex-col gap-3">
          {bossSlots.map(({ slot, info }) =>
            info ? (
              <CardVisual
                key={slot}
                type="boss"
                name={info.name}
                statLeft={String(info.hp)}
                statRight={String(info.threshold)}
                actionLabel="⚔️ Affronta"
                width={SIDEBAR_CARD_W}
                onClick={() => onCardClick({
                  type: 'boss', name: info.name,
                  statLeft: String(info.hp), statRight: String(info.threshold),
                  subtitle: `${info.difficulty} · +${info.reward_licenze}L`,
                  effect: info.ability,
                  actionLabel: '⚔️ Affronta', onAction: () => onStartCombat(slot),
                })}
                onAction={() => onStartCombat(slot)}
              />
            ) : (
              <div key={slot} className="rounded-xl border border-slate-800/50 bg-slate-900/30 flex items-center justify-center text-slate-700 text-[10px] italic"
                style={{ height: Math.round(SIDEBAR_CARD_W * 1.45) }}>
                slot vuoto
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

// ─── PlayArea ─────────────────────────────────────────────────────────────────

export interface CellData {
  p: PlayerState
  isMe?: boolean
  corner: Corner
}

interface PlayAreaProps {
  rows: CellData[][]
  addonMarket1: AddonMarketInfo | null
  addonMarket2: AddonMarketInfo | null
  bossMarket1: BossMarketInfo | null
  bossMarket2: BossMarketInfo | null
  onCardClick: (c: CardInfo) => void
  onBuyAddon: (slot: 1 | 2) => void
  onStartCombat: (slot: 1 | 2) => void
  onEndTurn: () => void
}

export function PlayArea({
  rows,
  addonMarket1, addonMarket2,
  bossMarket1, bossMarket2,
  onCardClick, onBuyAddon, onStartCombat, onEndTurn,
}: PlayAreaProps) {
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      <LeftSidebar
        addonMarket1={addonMarket1}
        addonMarket2={addonMarket2}
        onCardClick={onCardClick}
        onBuyAddon={onBuyAddon}
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <div className="flex flex-col divide-y divide-slate-800 h-full">
          {rows.map((row, ri) => (
            <div key={ri} className="flex flex-1 divide-x divide-slate-800">
              {row.map((cell, ci) => (
                <div key={ci} className="flex-1 min-w-0 flex">
                  <PlayerCell
                    p={cell.p}
                    isMe={cell.isMe}
                    corner={cell.corner}
                    onCardClick={onCardClick}
                    onEndTurn={cell.isMe ? onEndTurn : undefined}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <BossSidebar
        bossMarket1={bossMarket1}
        bossMarket2={bossMarket2}
        onCardClick={onCardClick}
        onStartCombat={onStartCombat}
      />
    </div>
  )
}
