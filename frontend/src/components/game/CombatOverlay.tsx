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
      <div className={`${color} h-2 rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ─── CSS 3D Dice ───────────────────────────────────────────────────────────
const D = 80   // cube side px
const H = D / 2

// Ogni iterazione del roll percorre angoli diversi — sembra un dado che tumba
// Il settle "sbatte" sul tavolo: arriva da sopra (opacity 0, scala grande) poi rimbalza
const DICE_KEYFRAMES = `
@keyframes diceRoll {
  0%   { transform: rotateX(0deg)    rotateY(0deg)    rotateZ(0deg); }
  20%  { transform: rotateX(72deg)   rotateY(108deg)  rotateZ(14deg); }
  40%  { transform: rotateX(144deg)  rotateY(216deg)  rotateZ(-9deg); }
  60%  { transform: rotateX(216deg)  rotateY(324deg)  rotateZ(7deg); }
  80%  { transform: rotateX(288deg)  rotateY(432deg)  rotateZ(-4deg); }
  100% { transform: rotateX(360deg)  rotateY(540deg)  rotateZ(0deg); }
}
@keyframes diceSettle {
  0%   { transform: scale(2) translateY(-30px); opacity: 0; }
  16%  { transform: scale(1) translateY(5px);   opacity: 1; }
  32%  { transform: scale(0.85) translateY(8px); }
  46%  { transform: scale(1.08) translateY(-6px); }
  60%  { transform: scale(0.95) translateY(3px); }
  72%  { transform: scale(1.03) translateY(-2px); }
  83%  { transform: scale(0.98) translateY(1px); }
  92%  { transform: scale(1.01) translateY(0); }
  100% { transform: scale(1) translateY(0); opacity: 1; }
}
`

function DieFace({
  value,
  faceTransform,
  accent,
  dim,
}: {
  value: number
  faceTransform: string
  accent: string
  dim?: boolean
}) {
  const bg = dim
    ? 'linear-gradient(145deg, #111827 0%, #0a1020 100%)'
    : 'linear-gradient(145deg, #1e293b 0%, #0f172a 100%)'
  const fontSize = value >= 10 ? 28 : 36

  return (
    <div
      style={{
        position: 'absolute',
        width: D,
        height: D,
        transform: faceTransform,
        backfaceVisibility: 'hidden',
        WebkitBackfaceVisibility: 'hidden' as 'hidden',
        background: bg,
        border: `2px solid ${accent}`,
        borderRadius: '14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize,
        fontWeight: 900,
        color: accent,
        fontFamily: "'Courier New', monospace",
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.06), inset 0 -2px 0 rgba(0,0,0,0.4)`,
        userSelect: 'none',
      }}
    >
      {value}
    </div>
  )
}

type Phase = 'idle' | 'rolling' | 'settling' | 'done'

function DiceCube({ value, phase, result }: { value: number; phase: Phase; result: 'hit' | 'miss' | null }) {
  const mainAccent =
    (phase === 'done' || phase === 'idle') && result === 'hit' ? '#4ade80' :
    (phase === 'done' || phase === 'idle') && result === 'miss' ? '#f87171' :
    '#94a3b8'
  const sideAccent = '#1e3a5f'

  const animation =
    phase === 'rolling'  ? 'diceRoll 0.32s linear infinite' :
    phase === 'settling' ? 'diceSettle 0.72s cubic-bezier(0.2,0,0.2,1) forwards' :
    'none'

  // Valori facce laterali: d10 → facce opposte sommano a 11
  const back   = 11 - value
  const sides  = [2, 5, 7, 3] // right, left, top, bottom

  return (
    <div style={{ perspective: '500px', width: D, height: D }}>
      <div
        style={{
          width: D, height: D,
          position: 'relative',
          transformStyle: 'preserve-3d',
          animation,
          willChange: 'transform',
        }}
      >
        {/* Front — mostra il valore corrente */}
        <DieFace value={value}     faceTransform={`translateZ(${H}px)`}               accent={mainAccent} />
        {/* Back */}
        <DieFace value={back}      faceTransform={`rotateY(180deg) translateZ(${H}px)`} accent={sideAccent} dim />
        {/* Right */}
        <DieFace value={sides[0]}  faceTransform={`rotateY(90deg) translateZ(${H}px)`}  accent={sideAccent} dim />
        {/* Left */}
        <DieFace value={sides[1]}  faceTransform={`rotateY(-90deg) translateZ(${H}px)`} accent={sideAccent} dim />
        {/* Top */}
        <DieFace value={sides[2]}  faceTransform={`rotateX(90deg) translateZ(${H}px)`}  accent={sideAccent} dim />
        {/* Bottom */}
        <DieFace value={sides[3]}  faceTransform={`rotateX(-90deg) translateZ(${H}px)`} accent={sideAccent} dim />
      </div>
    </div>
  )
}

// ─── DiceDisplay ───────────────────────────────────────────────────────────
function DiceDisplay({ rolling, finalRoll, result }: {
  rolling: boolean
  finalRoll: number | null
  result: 'hit' | 'miss' | null
}) {
  const [displayRoll, setDisplayRoll] = useState(1)
  const [phase, setPhase]             = useState<Phase>('idle')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevFinal   = useRef<number | null>(null)

  useEffect(() => {
    if (rolling) {
      setPhase('rolling')
      intervalRef.current = setInterval(() => {
        setDisplayRoll(Math.floor(Math.random() * 10) + 1)
      }, 55)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (finalRoll !== null && finalRoll !== prevFinal.current) {
        prevFinal.current = finalRoll
        setDisplayRoll(finalRoll)
        setPhase('settling')
        const t = setTimeout(() => setPhase('done'), 720)
        return () => clearTimeout(t)
      }
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [rolling, finalRoll])

  const labelColor =
    result === 'hit'  ? 'text-green-400' :
    result === 'miss' ? 'text-red-400'   : 'text-slate-500'

  return (
    <div className="flex flex-col items-center gap-3">
      <style>{DICE_KEYFRAMES}</style>
      <DiceCube value={displayRoll} phase={phase} result={result} />
      {phase === 'done' && result && (
        <span className={`text-sm font-bold tracking-widest ${labelColor}`}>
          {result === 'hit' ? '✓ COLPITO' : '✗ MANCATO'}
        </span>
      )}
    </div>
  )
}

// ─── Main overlay ──────────────────────────────────────────────────────────
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

const ROLL_DURATION   = 1200  // ms animazione rolling
const SETTLE_DURATION =  720  // ms animazione settle
const ANIM_TOTAL = ROLL_DURATION + SETTLE_DURATION

export function CombatOverlay({
  boss, bossHp, playerHp, playerMaxHp, combatRound,
  hand, addons, lastDiceRoll, isMyTurn,
  onRollDice, onPlayCard, onUseAddon,
}: CombatOverlayProps) {
  const [rolling, setRolling]       = useState(false)
  const [shownRoll, setShownRoll]   = useState<LastDiceRoll | null>(null)
  const [expandedCard, setExpandedCard] = useState<CardInfo | null>(null)

  // HP mostrati — aggiornati SOLO dopo la fine dell'animazione dado
  const [displayedBossHp,   setDisplayedBossHp]   = useState(bossHp)
  const [displayedPlayerHp, setDisplayedPlayerHp] = useState(playerHp)
  const hpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Quando arriva un nuovo risultato dado: avvia animazione + ritarda aggiornamento HP
  useEffect(() => {
    if (!lastDiceRoll) return
    if (shownRoll?.roll === lastDiceRoll.roll && shownRoll?.result === lastDiceRoll.result) return

    setRolling(true)
    // Dopo rolling: settle
    const rollTimer = setTimeout(() => {
      setRolling(false)
      setShownRoll(lastDiceRoll)
    }, ROLL_DURATION)

    // Aggiorna HP solo dopo la fine dell'animazione settle
    if (hpTimerRef.current) clearTimeout(hpTimerRef.current)
    hpTimerRef.current = setTimeout(() => {
      setDisplayedBossHp(lastDiceRoll.boss_hp)
      setDisplayedPlayerHp(lastDiceRoll.player_hp)
    }, ANIM_TOTAL)

    return () => {
      clearTimeout(rollTimer)
      if (hpTimerRef.current) clearTimeout(hpTimerRef.current)
    }
  }, [lastDiceRoll])

  // Sincronizza HP subito quando non c'è animazione in corso
  // (primo mount, entrata in combattimento, danni da carte, ecc.)
  useEffect(() => {
    if (!rolling && !lastDiceRoll) {
      setDisplayedBossHp(bossHp)
      setDisplayedPlayerHp(playerHp)
    }
  }, [bossHp, playerHp, rolling, lastDiceRoll])

  const difficultyColor = {
    'Easy': 'text-green-400', 'Medium': 'text-yellow-400',
    'Hard': 'text-orange-400', 'Legendary': 'text-purple-400',
  }[boss.difficulty] ?? 'text-slate-400'

  return (
    <div className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm flex items-center justify-center p-2 overflow-y-auto">
      <div className="w-full max-w-2xl bg-slate-900 rounded-2xl border border-orange-900/50 shadow-2xl flex flex-col gap-4 p-4 my-auto">

        <div className="flex items-center">
          <span className="text-orange-400 font-bold text-xs tracking-widest uppercase">
            ⚔ Combattimento — Round {combatRound}
          </span>
        </div>

        {/* Boss */}
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
              <span className="font-mono"><span className="text-red-400 font-bold">{displayedBossHp}</span> / {boss.hp}</span>
            </div>
            <HpBar current={displayedBossHp} max={boss.hp} color="bg-red-600" />
          </div>
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span>I tuoi HP</span>
              <span className="font-mono"><span className="text-emerald-400 font-bold">{displayedPlayerHp}</span> / {playerMaxHp}</span>
            </div>
            <HpBar current={displayedPlayerHp} max={playerMaxHp} color="bg-emerald-600" />
          </div>
          {boss.ability && (
            <p className="text-xs text-slate-400 italic border-t border-slate-700 pt-2">{boss.ability}</p>
          )}
          {boss.reward_licenze > 0 && (
            <div className="text-xs text-amber-400">🏆 Ricompensa: {boss.reward_licenze} licenze</div>
          )}
        </div>

        {/* Dado */}
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-5 flex flex-col items-center gap-4">
          <DiceDisplay rolling={rolling} finalRoll={shownRoll?.roll ?? null} result={shownRoll?.result ?? null} />
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
                    type="addon" name={a.name} subtitle={a.is_tapped ? 'tap' : 'untapped'} width={90}
                    actionLabel={!a.is_tapped && isMyTurn ? 'Usa' : undefined}
                    onClick={() => setExpandedCard({
                      type: 'addon', name: a.name, effect: a.effect,
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

        {/* Mano */}
        {hand.length > 0 && (
          <div>
            <h3 className="text-xs text-slate-500 uppercase font-semibold mb-2">Carte in mano ({hand.length})</h3>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {hand.map(c => (
                <div key={c.hand_card_id} className="shrink-0">
                  <CardVisual
                    type="action" name={c.name} subtitle={`#${c.card_id} · ${c.card_type}`} width={90}
                    actionLabel={isMyTurn ? 'Gioca' : undefined}
                    onClick={() => setExpandedCard({
                      type: 'action', name: c.name, subtitle: `#${c.card_id} · ${c.card_type}`,
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
