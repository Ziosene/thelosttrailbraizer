/**
 * PREVIEW ONLY — file temporaneo per approvare il layout della GamePage.
 * Da eliminare dopo la scelta.
 */

import { useState } from 'react'

type CardInfo = {
  name: string
  type: 'boss' | 'addon' | 'action'
  subtitle?: string
  statLeft?: string
  statRight?: string
  reward?: string
}

// ─── Dati finti (varianti addon per testare) ──────────────────────────────────

const ADDON_POOL = [
  'Einstein Insights',
  'FOMO Trigger (tappato)',
  'Apex Shield',
  'Batch Scheduler',
  'Rollup Summary',
  'Quick Deploy',
  'Async Callout',
  'Platform Event',
  'Kanban Board',
  'Tech Debt (tappato)',
  'Release Train',
  'Gov Limits Cap',
  'Sandbox Preview',
  'CDC Recover',
  'Future Method',
  'Pub/Sub Relay',
  'OmniStudio Flow',
  'Permission Set (tappato)',
  'Named Credential',
  'External ID',
  'Schema Builder',
  'Flow Orchestrator',
  'Custom Metadata',
  'Shield Platform',
  'MuleSoft Bridge (tappato)',
  'Data Loader',
  'Change Set',
  'Scratch Org',
  'DevHub Link',
  'ISV License (tappato)',
  'LWC Booster',
  'Aura Bridge',
  'Visualforce Ghost',
  'SOQL Optimizer',
  'SOSL Hunter',
  'Bulk API Relay',
  'Streaming API',
  'REST Proxy',
  'OAuth Token (tappato)',
  'JWT Handler',
  'Heroku Connect',
  'Salesforce Functions',
  'Shield Encrypt',
  'Event Replay',
  'Archive Policy',
  'Reporting Engine',
  'Dashboard Widget',
  'Formula Field',
  'Duplicate Rule',
  'Validation Script (tappato)',
]

function makePlayer(nickname: string, seniority: string, role: string, hp: number, max_hp: number, licenze: number, certs: number, addonCount: number) {
  return { nickname, seniority, role, hp, max_hp, licenze, certificazioni: certs, addons: ADDON_POOL.slice(0, addonCount) }
}

const ADDON_VARIANTS: Record<string, ReturnType<typeof makePlayer>[]> = {
  '0': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 0),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 0),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 0),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 0),
  ],
  '3': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 2),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 3),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 2),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 3),
  ],
  '6': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 4),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 6),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 5),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 6),
  ],
  '10': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 7),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 10),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 8),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 10),
  ],
  '16': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 10),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 16),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 12),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 16),
  ],
  '20': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 15),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 20),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 18),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 20),
  ],
  '30': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 22),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 30),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 26),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 30),
  ],
  '50': [
    makePlayer('Mario', 'Junior',      'Administrator',           1, 1, 3,  1, 38),
    makePlayer('Sara',  'Evangelist',  'CTA',                    2, 4, 12, 3, 50),
    makePlayer('Luca',  'Experienced', 'Sales Cloud Consultant', 2, 2, 5,  0, 44),
    makePlayer('Tu',    'Senior',      'Platform Developer I',   3, 3, 7,  2, 50),
  ],
}

const BOSSES   = [{ name: 'The Eternal Backlog', hp: 5, threshold: 7 }, { name: 'Apex Governor Limits', hp: 3, threshold: 5 }]
const ADDONS_M = [{ name: 'Einstein Insights', cost: 10, rarity: 'Raro' }, { name: 'FOMO Trigger', cost: 8, rarity: 'Non comune' }]
const HAND     = [
  { id: 1,  number: 12,  name: 'Data Migration',     type: 'Economica' },
  { id: 2,  number: 47,  name: 'Apex Trigger',        type: 'Offensiva' },
  { id: 3,  number: 88,  name: 'Shield Protocol',     type: 'Difensiva' },
  { id: 4,  number: 134, name: 'Role Hijack',          type: 'Interferenza' },
  { id: 5,  number: 22,  name: 'Bulk Upsert',          type: 'Economica' },
  { id: 6,  number: 61,  name: 'Governor Bypass',      type: 'Offensiva' },
  { id: 7,  number: 99,  name: 'Rollback Script',      type: 'Difensiva' },
  { id: 8,  number: 145, name: 'Phishing Deploy',      type: 'Interferenza' },
  { id: 9,  number: 37,  name: 'License Farming',      type: 'Economica' },
  { id: 10, number: 78,  name: 'Critical Patch',       type: 'Offensiva' },
]

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

// ─── Cella giocatore ──────────────────────────────────────────────────────────
// L'info card usa CSS float: gli addon si avvolgono attorno ad essa naturalmente.

type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'bottom-full' | 'top-full'

interface Player {
  nickname: string; seniority: string; role: string
  hp: number; max_hp: number; licenze: number; certificazioni: number; addons: string[]
}

function PlayerCell({ p, isMe, corner, onCardClick }: { p: Player; isMe?: boolean; corner: Corner; onCardClick: (c: CardInfo) => void }) {
  const isRight = corner === 'top-right' || corner === 'bottom-right'
  const bg = isMe ? 'bg-violet-950/25' : 'bg-slate-900/40'
  const floatSide: 'left' | 'right' = isRight ? 'left' : 'right'

  return (
    <div className={`flex-1 ${bg} p-2`}>
      {/* Info card floated — gli addon la circondano automaticamente */}
      <div
        style={{ float: floatSide, margin: '4px 6px 6px 4px' }}
        className={`flex flex-col gap-1 p-2 rounded-xl
          ${isMe ? 'bg-violet-900/30 border border-violet-700/40' : 'bg-slate-800/60 border border-slate-700/40'}`}
      >
        <div className={`font-bold text-xs ${isMe ? 'text-violet-300' : 'text-slate-200'}`}>{p.nickname}</div>
        <div className="text-slate-500 text-[10px] leading-tight max-w-[130px] truncate">{p.seniority} · {p.role}</div>
        <div className="flex items-center gap-2 flex-wrap">
          <HP cur={p.hp} max={p.max_hp} />
          <span className="text-yellow-400 text-[10px] font-semibold">💰{p.licenze}L</span>
        </div>
        <Certs count={p.certificazioni} />
        {isMe && (
          <button className="mt-1 bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg py-1 px-3 text-xs font-semibold transition-colors">
            Fine turno
          </button>
        )}
      </div>

      {/* Addon inline-block: scorrono attorno al float */}
      <div className={isRight ? 'text-right' : 'text-left'}>
        {p.addons.length === 0 && (
          <span className="text-slate-700 text-[10px] italic">nessun addon</span>
        )}
        {p.addons.map((a, i) => (
          <div
            key={i}
            style={{ display: 'inline-block', margin: '3px', verticalAlign: 'top' }}
            className={a.includes('tappato') ? 'opacity-35 grayscale' : ''}
          >
            <CardVisual
              type="addon" name={a} width={70}
              onClick={() => onCardClick({ type: 'addon', name: a })}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Carta visuale ────────────────────────────────────────────────────────────
// Componente generico a forma di carta fisica, pronto per ricevere immagini reali.

interface CardVisualProps {
  name: string
  subtitle?: string
  statLeft?: string
  statRight?: string
  reward?: string
  type: 'boss' | 'addon' | 'action'
  onClick?: () => void
  actionLabel?: string
  width?: number
}

const CARD_BORDER: Record<string, string> = {
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

function CardVisual({ name, subtitle, statLeft, statRight, reward, type, onClick, actionLabel, width = 110 }: CardVisualProps) {
  const aspectH = Math.round(width * 1.45)
  return (
    <div
      onClick={onClick}
      style={{ width, minWidth: width, height: aspectH }}
      className={`relative flex flex-col rounded-xl border-2 overflow-hidden cursor-pointer transition-all duration-150 hover:scale-105 shadow-lg
        ${CARD_BORDER[type]} bg-stone-950`}
    >
      {/* Intestazione carta */}
      <div className={`px-2 py-1 text-center text-[10px] font-bold leading-tight ${CARD_HEADER[type]}`}>
        {name}
      </div>

      {/* Arte (placeholder — sostituire con <img> quando disponibile) */}
      <div className={`flex-1 flex items-center justify-center ${CARD_ART_BG[type]}`}>
        <span className="text-3xl opacity-30">
          {type === 'boss' ? '👾' : type === 'addon' ? '🔧' : '🃏'}
        </span>
      </div>

      {/* Stats bar */}
      {(statLeft || statRight) && (
        <div className="bg-stone-900/90 px-2 py-1 flex justify-between items-center">
          {statLeft  && <span className="text-[10px] text-red-300 font-bold">❤️ {statLeft}</span>}
          {statRight && <span className="text-[10px] text-slate-300 font-bold">🎲 {statRight}+</span>}
        </div>
      )}

      {/* Sottotitolo (effetto / costo) */}
      {subtitle && (
        <div className="bg-stone-950/90 px-2 py-0.5 text-center text-[9px] text-slate-400 leading-tight">
          {subtitle}
        </div>
      )}

      {/* Ricompensa */}
      {reward && (
        <div className="bg-stone-900 px-2 py-0.5 text-center text-[9px] text-amber-300 font-semibold">
          {reward}
        </div>
      )}

      {/* Pulsante azione */}
      {actionLabel && (
        <button
          onClick={e => { e.stopPropagation(); onClick?.() }}
          className="bg-slate-800/90 hover:bg-slate-700 text-[10px] font-semibold text-slate-200 py-1 transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

// ─── Boss sidebar — sempre visibile a destra ──────────────────────────────────

// ─── Larghezza condivisa sidebar ─────────────────────────────────────────────
const SIDEBAR_W = 'w-48'       // 192px
const SIDEBAR_CARD_W = 152     // 192 - padding 2×p-3(12px) - scrollbar ~4px ≈ 152px

function BossSidebar({ onCardClick }: { onCardClick: (c: CardInfo) => void }) {
  return (
    <div className={`${SIDEBAR_W} shrink-0 border-l border-slate-800 bg-slate-900/60 flex flex-col gap-4 p-3 overflow-y-auto min-h-0 self-stretch`}>
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Boss attivi</div>
        <div className="flex flex-col gap-3">
          {BOSSES.map((b, i) => (
            <CardVisual
              key={i}
              type="boss"
              name={b.name}
              statLeft={String(b.hp)}
              statRight={String(b.threshold)}
              reward="4 📜📜📜"
              actionLabel="⚔️ Affronta"
              width={SIDEBAR_CARD_W}
              onClick={() => onCardClick({ type: 'boss', name: b.name, statLeft: String(b.hp), statRight: String(b.threshold), reward: '4 📜📜📜' })}
            />
          ))}
        </div>
      </div>

      {/* Mazzi boss */}
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Mazzo boss</div>
        <div className="flex flex-col gap-2">
          {[
            { label: 'Mazzo 1', count: 18, color: 'border-orange-700/60 bg-orange-950/30' },
            { label: 'Mazzo 2', count: 12, color: 'border-red-700/60 bg-red-950/30' },
          ].map(deck => (
            <div key={deck.label} className={`flex items-center justify-between rounded-xl border ${deck.color} px-3 py-2`}>
              <div className="flex items-center gap-2">
                {/* Carte impilate visivamente */}
                <div className="relative w-8 h-10">
                  <div className="absolute inset-0 rounded-md bg-slate-700 border border-slate-600" style={{ transform: 'rotate(-4deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-600 border border-slate-500" style={{ transform: 'rotate(-2deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-800 border border-slate-600 flex items-center justify-center">
                    <span className="text-slate-400 text-[14px]">👾</span>
                  </div>
                </div>
                <div>
                  <div className="text-slate-300 text-[11px] font-semibold">{deck.label}</div>
                  <div className="text-slate-500 text-[10px]">{deck.count} carte</div>
                </div>
              </div>
              <button className="text-[10px] bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg px-2 py-1 text-slate-200 transition-colors font-semibold">
                Pesca
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Sidebar sinistra — sempre visibile ──────────────────────────────────────

function LeftSidebar({ onCardClick }: { onCardClick: (c: CardInfo) => void }) {
  return (
    <div className={`${SIDEBAR_W} shrink-0 border-r border-slate-800 bg-slate-900/60 flex flex-col gap-4 p-3 overflow-y-auto min-h-0 self-stretch`}>
      {/* Addon da acquistare */}
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Addon mercato</div>
        <div className="flex flex-col gap-2">
          {ADDONS_M.map((a, i) => (
            <CardVisual
              key={i}
              type="addon"
              name={a.name}
              subtitle={`${a.cost}L · ${a.rarity}`}
              actionLabel="+ Acquista"
              width={SIDEBAR_CARD_W}
              onClick={() => onCardClick({ type: 'addon', name: a.name, subtitle: `${a.cost}L · ${a.rarity}` })}
            />
          ))}
        </div>
      </div>

      {/* Mazzi azioni */}
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Mazzo azioni</div>
        <div className="flex flex-col gap-2">
          {[
            { label: 'Mazzo 1', count: 42, color: 'border-violet-700/60 bg-violet-950/30', icon: '⚡' },
            { label: 'Mazzo 2', count: 38, color: 'border-blue-700/60 bg-blue-950/30',   icon: '⚡' },
          ].map(deck => (
            <div key={deck.label} className={`flex items-center justify-between rounded-xl border ${deck.color} px-3 py-2`}>
              <div className="flex items-center gap-2">
                <div className="relative w-8 h-10">
                  <div className="absolute inset-0 rounded-md bg-slate-700 border border-slate-600" style={{ transform: 'rotate(-4deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-600 border border-slate-500" style={{ transform: 'rotate(-2deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-800 border border-slate-600 flex items-center justify-center">
                    <span className="text-slate-400 text-[14px]">{deck.icon}</span>
                  </div>
                </div>
                <div>
                  <div className="text-slate-300 text-[11px] font-semibold">{deck.label}</div>
                  <div className="text-slate-500 text-[10px]">{deck.count} carte</div>
                </div>
              </div>
              <button className="text-[10px] bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg px-2 py-1 text-slate-200 transition-colors font-semibold">
                Pesca
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Mazzi addon */}
      <div>
        <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-2">Mazzo addon</div>
        <div className="flex flex-col gap-2">
          {[
            { label: 'Mazzo 1', count: 17, color: 'border-emerald-700/60 bg-emerald-950/30', icon: '🔧' },
            { label: 'Mazzo 2', count: 19, color: 'border-teal-700/60 bg-teal-950/30',       icon: '🔧' },
          ].map(deck => (
            <div key={deck.label} className={`flex items-center justify-between rounded-xl border ${deck.color} px-3 py-2`}>
              <div className="flex items-center gap-2">
                <div className="relative w-8 h-10">
                  <div className="absolute inset-0 rounded-md bg-slate-700 border border-slate-600" style={{ transform: 'rotate(-4deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-600 border border-slate-500" style={{ transform: 'rotate(-2deg)' }} />
                  <div className="absolute inset-0 rounded-md bg-slate-800 border border-slate-600 flex items-center justify-center">
                    <span className="text-slate-400 text-[14px]">{deck.icon}</span>
                  </div>
                </div>
                <div>
                  <div className="text-slate-300 text-[11px] font-semibold">{deck.label}</div>
                  <div className="text-slate-500 text-[10px]">{deck.count} carte</div>
                </div>
              </div>
              <button className="text-[10px] bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg px-2 py-1 text-slate-200 transition-colors font-semibold">
                Pesca
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Play area ────────────────────────────────────────────────────────────────

interface Cell { p: Player; isMe?: boolean; corner: Corner }

function PlayArea({ rows, onCardClick }: { rows: Cell[][]; onCardClick: (c: CardInfo) => void }) {
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      <LeftSidebar onCardClick={onCardClick} />
      {/* Grid: h-full → divisione uguale senza addon; overflow quando crescono */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <div className="flex flex-col divide-y divide-slate-800 h-full">
          {rows.map((row, ri) => (
            <div key={ri} className="flex flex-1 divide-x divide-slate-800">
              {row.map((cell, ci) => (
                <div key={ci} className="flex-1 min-w-0 flex">
                  <PlayerCell p={cell.p} isMe={cell.isMe} corner={cell.corner} onCardClick={onCardClick} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <BossSidebar onCardClick={onCardClick} />
    </div>
  )
}

// ─── Card Overlay — ingrandisce qualsiasi carta al centro ─────────────────────

function CardOverlay({ card, onClose }: { card: CardInfo; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div onClick={e => e.stopPropagation()}>
        <CardVisual
          type={card.type}
          name={card.name}
          subtitle={card.subtitle}
          statLeft={card.statLeft}
          statRight={card.statRight}
          reward={card.reward}
          width={280}
        />
      </div>
    </div>
  )
}

// ─── Log Panel — sidebar destra ───────────────────────────────────────────────

const LOG = [
  '⚔️ Sara ha affrontato Apex Governor Limits',
  '🎲 Sara — tiro 8 → HIT! Boss HP: 3→2',
  '🃏 Mario ha giocato Data Migration',
  '💰 Mario +2 licenze',
  '🔧 Tu hai acquistato Einstein Insights',
  '🎲 Tu — tiro 4 → MISS! HP: 3→2',
  '🃏 Tu hai giocato Apex Trigger',
  '💥 Mario ha perso 1 HP',
]

function LogPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed top-0 right-0 h-full w-64 z-40 bg-slate-900 border-l border-slate-700 flex flex-col shadow-2xl">
      <div className="flex justify-between items-center px-4 py-3 border-b border-slate-800 shrink-0">
        <span className="text-slate-300 font-semibold text-sm">Log partita</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-xl leading-none">×</button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {LOG.map((e, i) => (
          <div key={i} className="text-slate-400 text-xs border-b border-slate-800/60 pb-2 last:border-0">{e}</div>
        ))}
      </div>
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export function GamePagePreview() {
  const [nPlayers, setNPlayers] = useState<2 | 3 | 4>(4)
  const [addonVariant, setAddonVariant] = useState('3')
  const [logOpen, setLogOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<CardInfo | null>(null)

  const players = ADDON_VARIANTS[addonVariant]
  const [opp1, opp2, opp3, me] = players

  const rows2: Cell[][] = [
    [{ p: opp1, corner: 'top-full' }],
    [{ p: me, isMe: true, corner: 'bottom-full' }],
  ]
  const rows3: Cell[][] = [
    [{ p: opp1, corner: 'top-left' }, { p: opp2, corner: 'top-right' }],
    [{ p: me, isMe: true, corner: 'bottom-full' }],
  ]
  const rows4: Cell[][] = [
    [{ p: opp1, corner: 'top-left' }, { p: opp2, corner: 'top-right' }],
    [{ p: opp3, corner: 'bottom-left' }, { p: me, isMe: true, corner: 'bottom-right' }],
  ]

  const rows = nPlayers === 2 ? rows2 : nPlayers === 3 ? rows3 : rows4

  return (
    <div className="h-screen bg-slate-950 flex flex-col text-slate-200 text-sm overflow-hidden select-none">

      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center gap-3 text-xs shrink-0 flex-wrap">
        <span className="text-violet-400 font-bold">The Lost Trailbraizer</span>
        <span className="text-slate-700">|</span>
        <span className="text-slate-400">Turno <span className="text-white font-semibold">3</span></span>
        <span className="bg-amber-800/70 text-amber-200 px-2 py-0.5 rounded-full font-semibold">AZIONE</span>
        <span className="text-slate-400">→ <span className="text-violet-300 font-semibold">Tu</span></span>

        {/* Switcher giocatori */}
        <div className="flex gap-1 bg-slate-800 rounded-full p-0.5 ml-2">
          {([2, 3, 4] as const).map(n => (
            <button key={n} onClick={() => setNPlayers(n)}
              className={`px-3 py-0.5 rounded-full text-xs font-semibold transition-colors
                ${nPlayers === n ? 'bg-violet-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
              {n}P
            </button>
          ))}
        </div>

        {/* Switcher addon */}
        <div className="flex gap-1 bg-slate-800 rounded-full p-0.5">
          {Object.keys(ADDON_VARIANTS).map(v => (
            <button key={v} onClick={() => setAddonVariant(v)}
              className={`px-3 py-0.5 rounded-full text-xs font-semibold transition-colors
                ${addonVariant === v ? 'bg-emerald-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
              {v}
            </button>
          ))}
        </div>

        <div className="ml-auto">
          <button onClick={() => setLogOpen(v => !v)}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-1 text-slate-300 transition-colors">
            📋 Log
          </button>
        </div>
      </div>

      {/* Griglia + market */}
      <PlayArea rows={rows} onCardClick={setSelectedCard} />

      {/* Mano */}
      <div className="bg-slate-900/90 border-t border-slate-800 px-4 pt-3 pb-2 shrink-0">
        <div className="text-slate-600 text-xs uppercase tracking-wider mb-2">La tua mano ({HAND.length})</div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {HAND.map((c) => (
            <CardVisual
              key={c.id}
              type="action"
              name={c.name}
              subtitle={`#${c.number} · ${c.type}`}
              actionLabel="Gioca"
              width={90}
              onClick={() => setSelectedCard({ type: 'action', name: c.name, subtitle: `#${c.number} · ${c.type}` })}
            />
          ))}
        </div>
      </div>

      {logOpen && <LogPanel onClose={() => setLogOpen(false)} />}
      {selectedCard && <CardOverlay card={selectedCard} onClose={() => setSelectedCard(null)} />}
    </div>
  )
}
