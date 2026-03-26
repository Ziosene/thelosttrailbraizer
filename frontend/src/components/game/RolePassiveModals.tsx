import { useState } from 'react'
import type { BossPeekChoice, DrawPeekChoice } from '../../store/gameStore'

// ── Boss Peek Modal (Data Architect) ─────────────────────────────────────────

interface BossPeekModalProps {
  peek: BossPeekChoice
  onChoose: (bossCardId: number) => void
}

export function BossPeekModal({ peek, onChoose }: BossPeekModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-950 border border-cyan-700/50 rounded-2xl shadow-2xl p-6 flex flex-col gap-4 min-w-[360px] max-w-md w-full mx-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🔍</span>
          <span className="text-cyan-300 font-bold">Data Architect — Scegli il boss</span>
        </div>
        <p className="text-slate-400 text-xs">Guardi le prime carte del mazzo boss. Scegli quale affrontare:</p>
        <div className="flex flex-col gap-2">
          {peek.choices.map(boss => (
            <button
              key={boss.id}
              onClick={() => onChoose(boss.id)}
              className="text-left p-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-orange-600/60 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-orange-300">{boss.name}</span>
                <span className="text-xs text-slate-500">{boss.difficulty}</span>
              </div>
              <div className="flex gap-3 text-xs text-slate-400">
                <span>❤️ {boss.hp} HP</span>
                <span>🎲 soglia {boss.threshold}</span>
              </div>
              {boss.ability && (
                <div className="mt-1 text-[10px] text-slate-500 italic truncate">{boss.ability}</div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Draw Peek Modal (Data Cloud Consultant) ────────────────────────────────────

interface DrawPeekModalProps {
  peek: DrawPeekChoice
  onChoose: (cardId: number) => void
}

export function DrawPeekModal({ peek, onChoose }: DrawPeekModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-950 border border-cyan-700/50 rounded-2xl shadow-2xl p-6 flex flex-col gap-4 min-w-[360px] max-w-md w-full mx-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🔍</span>
          <span className="text-cyan-300 font-bold">Data Cloud Consultant — Scegli la carta</span>
        </div>
        <p className="text-slate-400 text-xs">Guardi le prime carte del mazzo azione. Scegli quale prendere:</p>
        <div className="flex flex-col gap-2">
          {peek.choices.map(card => (
            <button
              key={card.id}
              onClick={() => onChoose(card.id)}
              className="text-left p-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-violet-600/60 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-violet-300">{card.name}</span>
                <span className="text-xs text-slate-500">{card.card_type} · {card.rarity}</span>
              </div>
              {card.effect && (
                <div className="text-[10px] text-slate-400 italic line-clamp-2">{card.effect}</div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Einstein Prediction Modal (Einstein Analytics Consultant) ─────────────────

interface EinsteinPredictModalProps {
  onPredict: (value: number) => void
  onSkip: () => void
}

export function EinsteinPredictModal({ onPredict, onSkip }: EinsteinPredictModalProps) {
  const [selected, setSelected] = useState<number | null>(null)
  const dice = [1,2,3,4,5,6,7,8,9,10]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-950 border border-yellow-700/50 rounded-2xl shadow-2xl p-6 flex flex-col gap-4 min-w-[320px] max-w-sm w-full mx-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🎯</span>
          <span className="text-yellow-300 font-bold">Einstein Analytics — Dichiara il dado</span>
        </div>
        <p className="text-slate-400 text-xs">Se indovini il risultato esatto, il danno al boss è doppio.</p>
        <div className="grid grid-cols-5 gap-2">
          {dice.map(n => (
            <button
              key={n}
              onClick={() => setSelected(n)}
              className={`py-2 rounded-lg font-bold text-sm border transition-colors ${
                selected === n
                  ? 'bg-yellow-600 border-yellow-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-yellow-600'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => selected !== null && onPredict(selected)}
            disabled={selected === null}
            className="flex-1 py-2 rounded-xl bg-yellow-700 hover:bg-yellow-600 disabled:opacity-40 text-white font-semibold text-sm transition-colors"
          >
            Dichiara {selected ?? '—'}
          </button>
          <button
            onClick={onSkip}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 text-sm transition-colors"
          >
            Salta
          </button>
        </div>
      </div>
    </div>
  )
}
