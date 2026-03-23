import { useEffect, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { useAuthStore } from '../store/authStore'
import type { PlayerState, PublicAddon, AddonMarketInfo, BossMarketInfo } from '../types/game'
import { ReactionWindowModal, CardChoiceModal } from '../components/game/GameModals'

// ─── Tipi locali ──────────────────────────────────────────────────────────────

type CardInfo = {
  name: string
  type: 'boss' | 'addon' | 'action'
  subtitle?: string
  statLeft?: string
  statRight?: string
  reward?: string
}

type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'bottom-full' | 'top-full'

// ─── Costanti sidebar ─────────────────────────────────────────────────────────

const SIDEBAR_W = 'w-48'
const SIDEBAR_CARD_W = 152

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

// ─── Carta visuale ────────────────────────────────────────────────────────────

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

function CardVisual({ name, subtitle, statLeft, statRight, reward, type, onClick, actionLabel, onAction, width = 110 }: CardVisualProps) {
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

      {/* Arte placeholder */}
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

      {/* Sottotitolo */}
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
          onClick={e => { e.stopPropagation(); onAction?.() }}
          className="bg-slate-800/90 hover:bg-slate-700 text-[10px] font-semibold text-slate-200 py-1 transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

// ─── Card Overlay ─────────────────────────────────────────────────────────────

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

// ─── Deck card visual ─────────────────────────────────────────────────────────

function DeckCard({ icon, label, count, accent, onDraw }: {
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

// ─── Left Sidebar ─────────────────────────────────────────────────────────────

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
      {/* Addon mercato */}
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
                onClick={() => onCardClick({ type: 'addon', name: info.name, subtitle: `${info.cost}L · ${info.rarity}` })}
                onAction={() => onBuyAddon(slot)}
              />
            ) : (
              <div key={slot} className="rounded-xl border border-slate-800/50 bg-slate-900/30 flex items-center justify-center text-slate-700 text-[10px] italic" style={{ height: Math.round(SIDEBAR_CARD_W * 1.45) }}>
                slot vuoto
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Boss Sidebar ─────────────────────────────────────────────────────────────

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
      {/* Boss attivi */}
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
                onClick={() => onCardClick({ type: 'boss', name: info.name, statLeft: String(info.hp), statRight: String(info.threshold) })}
                onAction={() => onStartCombat(slot)}
              />
            ) : (
              <div key={slot} className="rounded-xl border border-slate-800/50 bg-slate-900/30 flex items-center justify-center text-slate-700 text-[10px] italic" style={{ height: Math.round(SIDEBAR_CARD_W * 1.45) }}>
                slot vuoto
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Player Cell ──────────────────────────────────────────────────────────────

interface PlayerCellProps {
  p: PlayerState
  isMe?: boolean
  corner: Corner
  onCardClick: (c: CardInfo) => void
  onEndTurn?: () => void
}

function PlayerCell({ p, isMe, corner, onCardClick, onEndTurn }: PlayerCellProps) {
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
              onClick={() => onCardClick({ type: 'addon', name: a.name })}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Play Area ────────────────────────────────────────────────────────────────

interface CellData {
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
  myUserId: number | null
}

function PlayArea({
  rows,
  addonMarket1, addonMarket2,
  bossMarket1, bossMarket2,
  onCardClick, onBuyAddon, onStartCombat, onEndTurn,
  myUserId,
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

// ─── Log Panel ────────────────────────────────────────────────────────────────

function LogPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed top-0 right-0 h-full w-64 z-40 bg-slate-900 border-l border-slate-700 flex flex-col shadow-2xl">
      <div className="flex justify-between items-center px-4 py-3 border-b border-slate-800 shrink-0">
        <span className="text-slate-300 font-semibold text-sm">Log partita</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-xl leading-none">×</button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="text-slate-600 text-xs italic">Nessun evento registrato.</div>
      </div>
    </div>
  )
}

// ─── GamePage ─────────────────────────────────────────────────────────────────

interface GamePageProps {
  gameCode: string
}

export function GamePage({ gameCode }: GamePageProps) {
  const { user } = useAuthStore()
  const { gameState, hand, myAddons, pendingChoice, reactionWindow, connect, disconnect, send, clearPendingChoice } = useGameStore()
  const [logOpen, setLogOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<CardInfo | null>(null)

  useEffect(() => {
    if (user) {
      connect(gameCode, user.id)
    }
    return () => {
      disconnect()
    }
  }, [gameCode, user?.id])

  if (!gameState) {
    return (
      <div className="h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-sm">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          Connessione in corso...
        </div>
      </div>
    )
  }

  const myUserId = user?.id ?? null
  const myPlayer = gameState.players.find(p => p.user_id === myUserId) ?? null
  const isMyTurn = myPlayer !== null && gameState.current_player_id === myPlayer.id

  // Ruota i giocatori in modo che "io" sia sempre l'ultimo
  const rotated = myPlayer
    ? [...gameState.players.filter(p => p.user_id !== myUserId), myPlayer]
    : [...gameState.players]

  const nPlayers = rotated.length

  // Costruisci le righe della griglia
  let rows: CellData[][]

  if (nPlayers <= 1) {
    // Caso degenere: un solo giocatore
    rows = [[{ p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'bottom-full' }]]
  } else if (nPlayers === 2) {
    rows = [
      [{ p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'top-full' }],
      [{ p: rotated[1], isMe: rotated[1].user_id === myUserId, corner: 'bottom-full' }],
    ]
  } else if (nPlayers === 3) {
    rows = [
      [
        { p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'top-left' },
        { p: rotated[1], isMe: rotated[1].user_id === myUserId, corner: 'top-right' },
      ],
      [{ p: rotated[2], isMe: rotated[2].user_id === myUserId, corner: 'bottom-full' }],
    ]
  } else {
    // 4+ giocatori: griglia 2x2, gli extra si appendono nella riga 1
    const topRow: CellData[] = rotated.slice(0, nPlayers - 2).map((p, i) => ({
      p,
      isMe: p.user_id === myUserId,
      corner: (i % 2 === 0 ? 'top-left' : 'top-right') as Corner,
    }))
    rows = [
      topRow,
      [
        { p: rotated[nPlayers - 2], isMe: rotated[nPlayers - 2].user_id === myUserId, corner: 'bottom-left' },
        { p: rotated[nPlayers - 1], isMe: rotated[nPlayers - 1].user_id === myUserId, corner: 'bottom-right' },
      ],
    ]
  }

  // Nome del giocatore corrente per l'header
  const currentPlayer = gameState.players.find(p => p.id === gameState.current_player_id)
  const turnLabel = isMyTurn
    ? '→ Tu'
    : currentPlayer ? `→ ${currentPlayer.nickname}` : ''

  const phaseLabel = gameState.current_phase ?? ''

  return (
    <div className="h-screen bg-slate-950 flex flex-col text-slate-200 text-sm overflow-hidden select-none">

      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center gap-3 text-xs shrink-0 flex-wrap">
        <span className="text-violet-400 font-bold">The Lost Trailbraizer</span>
        <span className="text-slate-700">|</span>
        <span className="text-slate-400">
          Turno <span className="text-white font-semibold">{gameState.turn_number}</span>
        </span>
        {phaseLabel && (
          <span className="bg-amber-800/70 text-amber-200 px-2 py-0.5 rounded-full font-semibold uppercase">
            {phaseLabel}
          </span>
        )}
        {turnLabel && (
          <span className="text-slate-400">
            <span className={isMyTurn ? 'text-violet-300 font-semibold' : 'text-slate-300 font-semibold'}>
              {turnLabel}
            </span>
          </span>
        )}
        <span className="text-slate-600 text-[10px]">#{gameCode}</span>

        <div className="ml-auto">
          <button
            onClick={() => setLogOpen(v => !v)}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-1 text-slate-300 transition-colors"
          >
            📋 Log
          </button>
        </div>
      </div>

      {/* Griglia + market */}
      <PlayArea
        rows={rows}
        addonMarket1={gameState.addon_market_1}
        addonMarket2={gameState.addon_market_2}
        bossMarket1={gameState.boss_market_1}
        bossMarket2={gameState.boss_market_2}
        onCardClick={setSelectedCard}
        onBuyAddon={(slot) => send('buy_addon', { market_slot: slot })}
        onStartCombat={(slot) => send('start_combat', { market_slot: slot })}
        onEndTurn={() => send('end_turn')}
        myUserId={myUserId}
      />

      {/* Mano + Mazzi */}
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
                  onClick={() => setSelectedCard({ type: 'action', name: c.name, subtitle: `#${c.card_id} · ${c.card_type}` })}
                  onAction={() => send('play_card', { hand_card_id: c.hand_card_id })}
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
                onDraw={() => send('draw_card', { deck: 1 })} />
              <DeckCard icon="⚡" label="Mazzo 2" count={gameState.action_deck_2_count} accent="border-blue-600/70"
                onDraw={() => send('draw_card', { deck: 2 })} />
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

      {logOpen && <LogPanel onClose={() => setLogOpen(false)} />}
      {selectedCard && <CardOverlay card={selectedCard} onClose={() => setSelectedCard(null)} />}

      {reactionWindow && (
        <ReactionWindowModal
          rw={reactionWindow}
          hand={hand}
          onPlay={(hcId) => send('play_reaction', { hand_card_id: hcId })}
          onPass={() => send('pass_reaction')}
        />
      )}

      {pendingChoice && (
        <CardChoiceModal
          choice={pendingChoice}
          hand={hand}
          myAddons={myAddons}
          onSubmit={(data) => {
            send('card_choice', { choice_type: pendingChoice.choice_type, ...data })
            clearPendingChoice()
          }}
        />
      )}
    </div>
  )
}
