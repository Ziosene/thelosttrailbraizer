import { useState } from 'react'
import type { DeathPenaltyChoice } from '../../store/gameStore'

interface Props {
  penalty: DeathPenaltyChoice
  onConfirm: (handCardId: number | null, playerAddonId: number | null) => void
}

export function DeathPenaltyModal({ penalty, onConfirm }: Props) {
  const [selectedCard, setSelectedCard] = useState<number | null>(null)
  const [selectedAddon, setSelectedAddon] = useState<number | null>(null)

  const hasCards = penalty.hand.length > 0
  const hasAddons = penalty.addons.length > 0

  const canConfirm =
    (!hasCards || selectedCard !== null) &&
    (!hasAddons || selectedAddon !== null)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="bg-slate-900 border border-red-800 rounded-2xl shadow-2xl p-6 w-full max-w-lg mx-4 flex flex-col gap-5">

        {/* Header */}
        <div className="text-center">
          <div className="text-3xl mb-1">💀</div>
          <h2 className="text-red-400 font-bold text-lg">Sei morto in combattimento</h2>
          <p className="text-slate-400 text-sm mt-1">
            Perdi <span className="text-red-400 font-semibold">1 Licenza</span> (applicata automaticamente).
            Scegli quale carta e quale addon perdere.
          </p>
        </div>

        {/* Card choice */}
        <div>
          <p className="text-slate-300 text-xs font-semibold uppercase tracking-wide mb-2">
            Carta da perdere {!hasCards && <span className="text-slate-600 font-normal">(nessuna carta in mano)</span>}
          </p>
          {hasCards ? (
            <div className="flex flex-wrap gap-2">
              {penalty.hand.map(hc => (
                <button
                  key={hc.hand_card_id}
                  onClick={() => setSelectedCard(hc.hand_card_id)}
                  className={`px-3 py-2 rounded-lg border text-sm transition-all ${
                    selectedCard === hc.hand_card_id
                      ? 'border-red-500 bg-red-900/40 text-red-300'
                      : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  <span className="font-semibold">{hc.name}</span>
                  <span className="text-slate-500 text-xs ml-1">({hc.card_type})</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-slate-600 text-sm italic">Nessuna carta disponibile</p>
          )}
        </div>

        {/* Addon choice */}
        <div>
          <p className="text-slate-300 text-xs font-semibold uppercase tracking-wide mb-2">
            AddOn da perdere {!hasAddons && <span className="text-slate-600 font-normal">(nessun addon)</span>}
          </p>
          {hasAddons ? (
            <div className="flex flex-wrap gap-2">
              {penalty.addons.map(pa => (
                <button
                  key={pa.player_addon_id}
                  onClick={() => setSelectedAddon(pa.player_addon_id)}
                  className={`px-3 py-2 rounded-lg border text-sm transition-all text-left ${
                    selectedAddon === pa.player_addon_id
                      ? 'border-red-500 bg-red-900/40 text-red-300'
                      : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  <span className="font-semibold">{pa.name}</span>
                  {pa.effect && (
                    <span className="block text-slate-500 text-xs mt-0.5 max-w-[200px] truncate">
                      {pa.effect}
                    </span>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-slate-600 text-sm italic">Nessun addon disponibile</p>
          )}
        </div>

        {/* Confirm */}
        <button
          disabled={!canConfirm}
          onClick={() => onConfirm(selectedCard, selectedAddon)}
          className={`w-full py-3 rounded-xl font-bold text-sm transition-all ${
            canConfirm
              ? 'bg-red-700 hover:bg-red-600 text-white'
              : 'bg-slate-800 text-slate-600 cursor-not-allowed'
          }`}
        >
          {canConfirm ? 'Conferma perdita' : 'Seleziona cosa perdere'}
        </button>
      </div>
    </div>
  )
}
