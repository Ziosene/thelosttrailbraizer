import { useState, useEffect, useRef } from 'react'
import type { BossMarketInfo, HandCard, HandAddon } from '../../types/game'
import type { LastDiceRoll } from '../../store/gameStore'

// ─── Dice faces (Unicode) ──────────────────────────────────────────────────
const DICE_FACES = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅', '⚅', '⚅', '⚅', '⚅'] // d10: show d6 faces + extra ⚅ for 7-10

function diceEmoji(n: number) {
  if (n <= 6) return DICE_FACES[n - 1]
  return '🎲'
}

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

// ─── Dice roller component ─────────────────────────────────────────────────
function DiceDisplay({ rolling, finalRoll, result }: {
  rolling: boolean
  finalRoll: number | null
  result: 'hit' | 'miss' | null
}) {
  const [displayRoll, setDisplayRoll] = useState<number>(1)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (rolling) {
      intervalRef.current = setInterval(() => {
        setDisplayRoll(Math.floor(Math.random() * 10) + 1)
      }, 80)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (finalRoll !== null) setDisplayRoll(finalRoll)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [rolling, finalRoll])

  const hitColor = result === 'hit' ? 'text-green-400' : result === 'miss' ? 'text-red-400' : 'text-slate-300'

  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`text-7xl transition-all ${rolling ? 'animate-bounce' : ''} ${hitColor}`}>
        {diceEmoji(displayRoll)}
      </span>
      <span className={`text-2xl font-bold tabular-nums ${hitColor}`}>
        {finalRoll !== null ? finalRoll : '?'}
      </span>
      {result && (
        <span className={`text-sm font-bold tracking-widest ${hitColor}`}>
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
  onRetreat: () => void
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
  onRetreat,
}: CombatOverlayProps) {
  const [rolling, setRolling] = useState(false)
  const [shownRoll, setShownRoll] = useState<LastDiceRoll | null>(null)
  const [expandedCard, setExpandedCard] = useState<number | null>(null)
  const [expandedAddon, setExpandedAddon] = useState<number | null>(null)

  // Animate when a new dice_rolled event arrives
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
          {isMyTurn && (
            <button
              onClick={onRetreat}
              className="text-xs text-slate-500 hover:text-red-400 border border-slate-700 hover:border-red-700 rounded px-2 py-1 transition-colors"
            >
              🏃 Ritirati
            </button>
          )}
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

          {/* Boss HP bar */}
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span>HP Boss</span>
              <span className="font-mono"><span className="text-red-400 font-bold">{bossHp}</span> / {boss.hp}</span>
            </div>
            <HpBar current={bossHp} max={boss.hp} color="bg-red-600" />
          </div>

          {/* Player HP */}
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span>I tuoi HP</span>
              <span className="font-mono"><span className="text-emerald-400 font-bold">{playerHp}</span> / {playerMaxHp}</span>
            </div>
            <HpBar current={playerHp} max={playerMaxHp} color="bg-emerald-600" />
          </div>

          {/* Boss ability */}
          {boss.ability && (
            <p className="text-xs text-slate-400 italic border-t border-slate-700 pt-2">{boss.ability}</p>
          )}

          {boss.reward_licenze > 0 && (
            <div className="text-xs text-amber-400">
              🏆 Ricompensa: {boss.reward_licenze} licenze
            </div>
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

        {/* Addons usabili */}
        {addons.length > 0 && (
          <div>
            <h3 className="text-xs text-slate-500 uppercase font-semibold mb-2">AddOn</h3>
            <div className="flex flex-wrap gap-2">
              {addons.map(a => {
                const isExpanded = expandedAddon === a.player_addon_id
                return (
                  <div key={a.player_addon_id} className="relative">
                    <button
                      onClick={() => setExpandedAddon(isExpanded ? null : a.player_addon_id)}
                      className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all ${
                        a.is_tapped
                          ? 'border-slate-700 text-slate-600 bg-slate-800/30 cursor-not-allowed'
                          : 'border-teal-700 text-teal-300 bg-teal-900/20 hover:bg-teal-900/40'
                      }`}
                    >
                      {a.name} {a.is_tapped ? '(tap)' : ''}
                    </button>
                    {isExpanded && (
                      <div className="absolute bottom-full mb-1 left-0 z-50 w-52 bg-slate-800 border border-slate-600 rounded-lg p-2 text-xs text-slate-300 shadow-xl">
                        <p className="font-semibold text-teal-300 mb-1">{a.name}</p>
                        <p className="text-slate-400 mb-2">{a.effect}</p>
                        {!a.is_tapped && isMyTurn && (
                          <button
                            onClick={() => { onUseAddon(a.player_addon_id); setExpandedAddon(null) }}
                            className="w-full py-1 bg-teal-700 hover:bg-teal-600 rounded text-white font-semibold"
                          >
                            Usa
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Carte in mano */}
        {hand.length > 0 && (
          <div>
            <h3 className="text-xs text-slate-500 uppercase font-semibold mb-2">Carte in mano ({hand.length})</h3>
            <div className="flex flex-wrap gap-2">
              {hand.map(c => {
                const isExpanded = expandedCard === c.hand_card_id
                const typeColor: Record<string, string> = {
                  Offensiva: 'border-red-700 text-red-300 bg-red-900/20',
                  Difensiva: 'border-blue-700 text-blue-300 bg-blue-900/20',
                  Utilità: 'border-purple-700 text-purple-300 bg-purple-900/20',
                  Economica: 'border-amber-700 text-amber-300 bg-amber-900/20',
                }
                const cls = typeColor[c.card_type] ?? 'border-slate-600 text-slate-300 bg-slate-800/30'
                return (
                  <div key={c.hand_card_id} className="relative">
                    <button
                      onClick={() => setExpandedCard(isExpanded ? null : c.hand_card_id)}
                      className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all hover:opacity-90 ${cls}`}
                    >
                      {c.name}
                    </button>
                    {isExpanded && (
                      <div className="absolute bottom-full mb-1 left-0 z-50 w-56 bg-slate-800 border border-slate-600 rounded-lg p-2 text-xs text-slate-300 shadow-xl">
                        <p className="font-semibold mb-0.5">{c.name}</p>
                        <p className="text-slate-500 mb-1">{c.card_type} · {c.rarity}</p>
                        <p className="text-slate-400 mb-2">{c.effect}</p>
                        {isMyTurn && (
                          <button
                            onClick={() => { onPlayCard(c.hand_card_id); setExpandedCard(null) }}
                            className="w-full py-1 bg-violet-700 hover:bg-violet-600 rounded text-white font-semibold"
                          >
                            Gioca
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
