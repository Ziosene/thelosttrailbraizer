import { useState, useEffect, useRef } from 'react'
import type { BossMarketInfo, HandCard, HandAddon } from '../../types/game'
import type { LastDiceRoll } from '../../store/gameStore'
import { CardVisual, CardOverlay } from './CardVisual'
import type { CardInfo } from './CardVisual'

// ─── HP Bar ────────────────────────────────────────────────────────────────
function HpBar({ current, max, color = 'bg-red-500' }: { current: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0
  return (
    <div className="w-full bg-slate-700 rounded-full h-2">
      <div
        className={`${color} h-2 rounded-full transition-all duration-500`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ─── D10 SVG ───────────────────────────────────────────────────────────────
// Classica forma a diamante allungato con punta inferiore
function DiceD10SVG({ value, result }: { value: number; result: 'hit' | 'miss' | null }) {
  const accent = result === 'hit' ? '#4ade80' : result === 'miss' ? '#f87171' : '#94a3b8'
  const glow   = result === 'hit' ? '#4ade8040' : result === 'miss' ? '#f8717140' : 'transparent'

  return (
    <svg viewBox="0 0 100 120" width={90} height={108} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id="d10top" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="d10bot" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#0f172a" />
          <stop offset="100%" stopColor="#020617" />
        </linearGradient>
        <filter id="glow">
          <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor={glow} />
        </filter>
      </defs>

      {/* Corpo superiore: pentagono d10 */}
      <polygon
        points="50,4 96,36 80,88 20,88 4,36"
        fill="url(#d10top)"
        stroke={accent}
        strokeWidth="2"
        filter="url(#glow)"
      />
      {/* Punta inferiore */}
      <polygon
        points="20,88 50,116 80,88"
        fill="url(#d10bot)"
        stroke={accent}
        strokeWidth="2"
        filter="url(#glow)"
      />

      {/* Linee di spigolo per look 3D */}
      <line x1="50" y1="4"  x2="20" y2="88" stroke={accent} strokeWidth="0.6" opacity="0.25" />
      <line x1="50" y1="4"  x2="80" y2="88" stroke={accent} strokeWidth="0.6" opacity="0.25" />
      <line x1="20" y1="88" x2="50" y2="116" stroke={accent} strokeWidth="0.6" opacity="0.25" />
      <line x1="80" y1="88" x2="50" y2="116" stroke={accent} strokeWidth="0.6" opacity="0.25" />
      <line x1="4"  y1="36" x2="96" y2="36"  stroke={accent} strokeWidth="0.5" opacity="0.15" />

      {/* Numero */}
      <text
        x="50" y="55"
        textAnchor="middle"
        dominantBaseline="middle"
        fill={accent}
        fontSize={value >= 10 ? '28' : '34'}
        fontWeight="bold"
        fontFamily="'Courier New', monospace"
        style={{ letterSpacing: '-1px' }}
      >
        {value}
      </text>
    </svg>
  )
}

// ─── Dice roller ───────────────────────────────────────────────────────────
const DICE_KEYFRAMES = `
@keyframes d10roll {
  0%   { transform: perspective(300px) rotateY(0deg)   rotateX(15deg)  scale(1);    filter: blur(0px); }
  15%  { transform: perspective(300px) rotateY(90deg)  rotateX(-10deg) scale(0.9);  filter: blur(1.5px); }
  30%  { transform: perspective(300px) rotateY(180deg) rotateX(15deg)  scale(1.05); filter: blur(2px); }
  50%  { transform: perspective(300px) rotateY(270deg) rotateX(-10deg) scale(0.95); filter: blur(1.5px); }
  70%  { transform: perspective(300px) rotateY(360deg) rotateX(15deg)  scale(1.02); filter: blur(1px); }
  85%  { transform: perspective(300px) rotateY(450deg) rotateX(-8deg)  scale(0.98); filter: blur(0.5px); }
  100% { transform: perspective(300px) rotateY(540deg) rotateX(12deg)  scale(1);    filter: blur(0px); }
}
@keyframes d10settle {
  0%   { transform: scale(1.3) rotateZ(-10deg); }
  40%  { transform: scale(1.12) rotateZ(6deg); }
  65%  { transform: scale(1.05) rotateZ(-3deg); }
  82%  { transform: scale(1.02) rotateZ(1deg); }
  100% { transform: scale(1) rotateZ(0deg); }
}
`

function DiceDisplay({ rolling, finalRoll, result }: {
  rolling: boolean
  finalRoll: number | null
  result: 'hit' | 'miss' | null
}) {
  const [displayRoll, setDisplayRoll] = useState<number>(1)
  const [settled, setSettled]         = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevFinal   = useRef<number | null>(null)

  useEffect(() => {
    if (rolling) {
      setSettled(false)
      intervalRef.current = setInterval(() => {
        setDisplayRoll(Math.floor(Math.random() * 10) + 1)
      }, 55)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (finalRoll !== null && finalRoll !== prevFinal.current) {
        prevFinal.current = finalRoll
        setDisplayRoll(finalRoll)
        setSettled(true)
        const t = setTimeout(() => setSettled(false), 500)
        return () => clearTimeout(t)
      }
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [rolling, finalRoll])

  const labelColor = result === 'hit' ? 'text-green-400' : result === 'miss' ? 'text-red-400' : 'text-slate-400'

  const animation = rolling
    ? 'd10roll 0.35s linear infinite'
    : settled
      ? 'd10settle 0.45s cubic-bezier(0.34,1.56,0.64,1) forwards'
      : 'none'

  return (
    <div className="flex flex-col items-center gap-2">
      <style>{DICE_KEYFRAMES}</style>
      <div style={{ animation, transformOrigin: 'center center', willChange: 'transform' }}>
        <DiceD10SVG value={displayRoll} result={rolling ? null : result} />
      </div>
      {result && !rolling && (
        <span className={`text-sm font-bold tracking-widest ${labelColor}`}>
          {result === 'hit' ? '✓ COLPITO' : '✗ MANCATO'}
        </span>
      )}
    </div>
  )
}

// ─── Main overlay ─────────────────────────────────────────────────────────
interface CombatOverlayProps {
  boss: BossMarketInfo
  bossHp: number
  playerHp: number
  playerMaxHp: number
  combatRound: number
  hand: HandCard[]
  addons: HandAddon[]
  lastDiceRoll: LastDiceRoll | null
  isMyTurn: boolean
  onRollDice: () => void
  onPlayCard: (handCardId: number) => void
  onUseAddon: (playerAddonId: number) => void
}

export function CombatOverlay({
  boss,
  bossHp,
  playerHp,
  playerMaxHp,
  combatRound,
  hand,
  addons,
  lastDiceRoll,
  isMyTurn,
  onRollDice,
  onPlayCard,
  onUseAddon,
}: CombatOverlayProps) {
  const [rolling, setRolling]       = useState(false)
  const [shownRoll, setShownRoll]   = useState<LastDiceRoll | null>(null)
  const [expandedCard, setExpandedCard] = useState<CardInfo | null>(null)

  useEffect(() => {
    if (!lastDiceRoll) return
    if (shownRoll?.roll === lastDiceRoll.roll && shownRoll?.result === lastDiceRoll.result) return
    setRolling(true)
    const timer = setTimeout(() => {
      setRolling(false)
      setShownRoll(lastDiceRoll)
    }, 1200)
    return () => clearTimeout(timer)
  }, [lastDiceRoll])

  const difficultyColor = {
    'Easy': 'text-green-400',
    'Medium': 'text-yellow-400',
    'Hard': 'text-orange-400',
    'Legendary': 'text-purple-400',
  }[boss.difficulty] ?? 'text-slate-400'

  return (
    <div className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm flex items-center justify-center p-2 overflow-y-auto">
      <div className="w-full max-w-2xl bg-slate-900 rounded-2xl border border-orange-900/50 shadow-2xl flex flex-col gap-4 p-4 my-auto">

        {/* Header */}
        <div className="flex items-center justify-between">
          <span className="text-orange-400 font-bold text-xs tracking-widest uppercase">
            ⚔ Combattimento — Round {combatRound}
          </span>
        </div>

        {/* Boss card */}
        <div className="bg-slate-800 rounded-xl border border-orange-800/40 p-4 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <h2 className="text-xl font-bold text-orange-300">{boss.name}</h2>
              <span className={`text-xs font-semibold ${difficultyColor}`}>{boss.difficulty}</span>
            </div>
            <div className="text-right shrink-0">
              <div className="text-xs text-slate-500">Soglia dado</div>
              <div className="text-2xl font-bold text-white">{boss.threshold}<span className="text-slate-500 text-sm">+</span></div>
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span>HP Boss</span>
              <span className="font-mono"><span className="text-red-400 font-bold">{bossHp}</span> / {boss.hp}</span>
            </div>
            <HpBar current={bossHp} max={boss.hp} color="bg-red-600" />
          </div>

          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span>I tuoi HP</span>
              <span className="font-mono"><span className="text-emerald-400 font-bold">{playerHp}</span> / {playerMaxHp}</span>
            </div>
            <HpBar current={playerHp} max={playerMaxHp} color="bg-emerald-600" />
          </div>

          {boss.ability && (
            <p className="text-xs text-slate-400 italic border-t border-slate-700 pt-2">{boss.ability}</p>
          )}
          {boss.reward_licenze > 0 && (
            <div className="text-xs text-amber-400">🏆 Ricompensa: {boss.reward_licenze} licenze</div>
          )}
        </div>

        {/* Dice roller */}
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-4 flex flex-col items-center gap-3">
          <DiceDisplay
            rolling={rolling}
            finalRoll={shownRoll?.roll ?? null}
            result={shownRoll?.result ?? null}
          />
          {isMyTurn && !rolling && (
            <button
              onClick={() => { setRolling(true); onRollDice() }}
              className="px-6 py-2 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-xl transition-colors text-sm"
            >
              🎲 Tira il dado
            </button>
          )}
          {!isMyTurn && (
            <p className="text-slate-500 text-sm">Non è il tuo turno</p>
          )}
        </div>

        {/* Addons */}
        {addons.length > 0 && (
          <div>
            <h3 className="text-xs text-slate-500 uppercase font-semibold mb-2">I tuoi AddOn</h3>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {addons.map(a => (
                <div key={a.player_addon_id} className={`shrink-0 ${a.is_tapped ? 'opacity-40' : ''}`}>
                  <CardVisual
                    type="addon"
                    name={a.name}
                    subtitle={a.is_tapped ? 'tap' : 'untapped'}
                    width={90}
                    actionLabel={!a.is_tapped && isMyTurn ? 'Usa' : undefined}
                    onClick={() => setExpandedCard({
                      type: 'addon',
                      name: a.name,
                      effect: a.effect,
                      actionLabel: !a.is_tapped && isMyTurn ? 'Usa' : undefined,
                      onAction: !a.is_tapped && isMyTurn ? () => onUseAddon(a.player_addon_id) : undefined,
                    })}
                    onAction={!a.is_tapped && isMyTurn ? () => onUseAddon(a.player_addon_id) : undefined}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Carte in mano */}
        {hand.length > 0 && (
          <div>
            <h3 className="text-xs text-slate-500 uppercase font-semibold mb-2">Carte in mano ({hand.length})</h3>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {hand.map(c => (
                <div key={c.hand_card_id} className="shrink-0">
                  <CardVisual
                    type="action"
                    name={c.name}
                    subtitle={`#${c.card_id} · ${c.card_type}`}
                    width={90}
                    actionLabel={isMyTurn ? 'Gioca' : undefined}
                    onClick={() => setExpandedCard({
                      type: 'action',
                      name: c.name,
                      subtitle: `#${c.card_id} · ${c.card_type}`,
                      effect: c.effect,
                      actionLabel: isMyTurn ? 'Gioca' : undefined,
                      onAction: isMyTurn ? () => onPlayCard(c.hand_card_id) : undefined,
                    })}
                    onAction={isMyTurn ? () => onPlayCard(c.hand_card_id) : undefined}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {expandedCard && (
        <CardOverlay card={expandedCard} onClose={() => setExpandedCard(null)} />
      )}
    </div>
  )
}
