/**
 * Modal interattivi per la partita:
 * - ReactionWindowModal: finestra di reazione out-of-turn (8s)
 * - CardChoiceModal: scelta per completare l'effetto di una carta
 */
import { useEffect, useState } from 'react'
import type { HandCard, HandAddon } from '../../types/game'
import type { PendingChoice, ReactionWindow, ComplyOrRefuse, DebugModePeek } from '../../store/gameStore'

// ─── Mini card per la selezione ───────────────────────────────────────────────

function SelectableCard({
  name,
  sub,
  selected,
  onClick,
}: {
  name: string
  sub?: string
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-xl border-2 p-2 text-left transition-all w-[88px]
        ${selected
          ? 'border-violet-400 bg-violet-900/40 shadow-lg shadow-violet-900/30'
          : 'border-slate-700 bg-slate-800/60 hover:border-slate-500'
        }`}
    >
      <div className="text-[10px] font-bold text-slate-200 leading-tight line-clamp-3 mb-1">{name}</div>
      {sub && <div className="text-[9px] text-slate-500 truncate">{sub}</div>}
      {selected && <div className="text-[9px] text-violet-400 font-bold mt-1">✓ selezionata</div>}
    </button>
  )
}

function ReorderList({
  items,
  label,
  onChange,
}: {
  items: { id: number; name: string }[]
  label: string
  onChange: (items: { id: number; name: string }[]) => void
}) {
  const move = (from: number, to: number) => {
    const arr = [...items]
    const [el] = arr.splice(from, 1)
    arr.splice(to, 0, el)
    onChange(arr)
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="text-slate-500 text-[10px] uppercase tracking-wider">{label}</div>
      {items.map((item, i) => (
        <div key={item.id} className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2">
          <span className="text-slate-400 text-xs font-mono w-4">{i + 1}.</span>
          <span className="flex-1 text-slate-200 text-xs font-semibold">{item.name}</span>
          <button
            onClick={() => i > 0 && move(i, i - 1)}
            disabled={i === 0}
            className="text-slate-500 hover:text-slate-200 disabled:opacity-20 text-sm px-1"
          >↑</button>
          <button
            onClick={() => i < items.length - 1 && move(i, i + 1)}
            disabled={i === items.length - 1}
            className="text-slate-500 hover:text-slate-200 disabled:opacity-20 text-sm px-1"
          >↓</button>
        </div>
      ))}
    </div>
  )
}

// ─── Reaction Window Modal ────────────────────────────────────────────────────

export function ReactionWindowModal({
  rw,
  hand,
  onPlay,
  onPass,
}: {
  rw: ReactionWindow
  hand: HandCard[]
  onPlay: (hcId: number) => void
  onPass: () => void
}) {
  const [remaining, setRemaining] = useState(Math.ceil(rw.timeout_ms / 1000))

  useEffect(() => {
    const id = setInterval(() => {
      const elapsed = Date.now() - rw.opened_at
      const rem = Math.max(0, Math.ceil((rw.timeout_ms - elapsed) / 1000))
      setRemaining(rem)
    }, 250)
    return () => clearInterval(id)
  }, [rw.opened_at, rw.timeout_ms])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center pb-36 bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border-2 border-amber-500/70 rounded-2xl p-4 mx-4 shadow-2xl w-full max-w-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-amber-400 font-bold text-sm">⚡ Finestra di reazione</span>
          <span className={`font-mono font-bold text-xl ${remaining <= 3 ? 'text-red-400 animate-pulse' : 'text-slate-200'}`}>
            {remaining}s
          </span>
        </div>
        <p className="text-slate-400 text-xs mb-3">
          Carta giocata: <span className="text-white font-semibold">{rw.trigger_card.name}</span>
          {' — '}clicca su una tua carta per reagire, oppure passa.
        </p>
        {hand.length > 0 ? (
          <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
            {hand.map(c => (
              <SelectableCard
                key={c.hand_card_id}
                name={c.name}
                sub={c.card_type}
                selected={false}
                onClick={() => onPlay(c.hand_card_id)}
              />
            ))}
          </div>
        ) : (
          <p className="text-slate-600 text-xs italic mb-3">Nessuna carta in mano.</p>
        )}
        <button
          onClick={onPass}
          className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl py-2 text-slate-300 font-semibold text-sm transition-colors"
        >
          Passa
        </button>
      </div>
    </div>
  )
}

// ─── Card Choice Modal ────────────────────────────────────────────────────────

export function CardChoiceModal({
  choice,
  hand,
  myAddons,
  onSubmit,
}: {
  choice: PendingChoice
  hand: HandCard[]
  myAddons: HandAddon[]
  onSubmit: (data: Record<string, unknown>) => void
}) {
  const { choice_type, count = 1, max_keep = 1, drawn_card_ids, options, action_card_ids, boss_card_ids, target_addon_options } = choice

  // ── Selezione multi-carta dalla mano (hand_card_id) ──────────────────────
  const [selectedHcIds, setSelectedHcIds] = useState<Set<number>>(new Set())
  const toggleHc = (id: number, maxSel: number) => {
    setSelectedHcIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) }
      else if (next.size < maxSel) { next.add(id) }
      return next
    })
  }

  // ── Selezione singola action_card_id (keep_one_from_drawn) ───────────────
  const [selectedAcId, setSelectedAcId] = useState<number | null>(null)

  // ── Selezione multi action_card_id (recover_from_discard) ────────────────
  const [selectedAcIds, setSelectedAcIds] = useState<Set<number>>(new Set())
  const toggleAc = (id: number, maxSel: number) => {
    setSelectedAcIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) }
      else if (next.size < maxSel) { next.add(id) }
      return next
    })
  }

  // ── Selezione singola addon (choose_addon_to_return) ─────────────────────
  const [selectedAddonId, setSelectedAddonId] = useState<number | null>(null)

  // ── Riordinamento (reorder_action_deck / reorder_boss_deck) ──────────────
  const [orderedList, setOrderedList] = useState<{ id: number; name: string }[]>(() => {
    const ids = action_card_ids ?? boss_card_ids ?? []
    return ids.map(id => ({ id, name: `Carta #${id}` }))
  })

  const titles: Record<string, string> = {
    discard_specific_cards: `Scegli ${count} carte da scartare`,
    return_card_to_deck_top: 'Scegli 1 carta da rimettere in cima al mazzo',
    keep_one_from_drawn: 'Scegli 1 carta da tenere',
    choose_cards_to_keep: `Scegli fino a ${max_keep} carte da tenere`,
    recover_from_discard: `Scegli ${count} carte dal mazzo degli scarti`,
    choose_addon_to_return: 'Scegli un addon da restituire',
    delete_target_addon: 'Scegli quale addon eliminare',
    reorder_action_deck: 'Riordina le carte azione in cima al mazzo',
    reorder_boss_deck: 'Riordina i boss in cima al mazzo',
  }

  // Filtra le mano mostrate per le choice che operano sulle drawn cards
  const drawnHand = drawn_card_ids
    ? hand.filter(c => drawn_card_ids.includes(c.card_id))
    : hand

  const handleSubmit = () => {
    switch (choice_type) {
      case 'discard_specific_cards':
        if (selectedHcIds.size !== count) return
        onSubmit({ hand_card_ids: [...selectedHcIds] })
        break
      case 'return_card_to_deck_top':
        if (selectedHcIds.size !== 1) return
        onSubmit({ hand_card_id: [...selectedHcIds][0] })
        break
      case 'keep_one_from_drawn':
        if (selectedAcId === null) return
        onSubmit({ action_card_id: selectedAcId })
        break
      case 'choose_cards_to_keep':
        onSubmit({ hand_card_ids: [...selectedHcIds] })
        break
      case 'recover_from_discard':
        if (selectedAcIds.size !== count) return
        onSubmit({ action_card_ids: [...selectedAcIds] })
        break
      case 'choose_addon_to_return':
        if (selectedAddonId === null) return
        onSubmit({ player_addon_id: selectedAddonId })
        break
      case 'delete_target_addon':
        if (selectedAddonId === null) return
        onSubmit({ player_addon_id: selectedAddonId })
        break
      case 'reorder_action_deck':
        onSubmit({ action_card_ids: orderedList.map(i => i.id) })
        break
      case 'reorder_boss_deck':
        onSubmit({ boss_card_ids: orderedList.map(i => i.id) })
        break
      default:
        onSubmit({})
    }
  }

  const canSubmit = () => {
    switch (choice_type) {
      case 'discard_specific_cards': return selectedHcIds.size === count
      case 'return_card_to_deck_top': return selectedHcIds.size === 1
      case 'keep_one_from_drawn': return selectedAcId !== null
      case 'choose_cards_to_keep': return true
      case 'recover_from_discard': return selectedAcIds.size === count
      case 'choose_addon_to_return':
      case 'delete_target_addon': return selectedAddonId !== null
      case 'reorder_action_deck':
      case 'reorder_boss_deck': return true
      default: return true
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 shadow-2xl w-full max-w-xl max-h-[80vh] flex flex-col">
        <div className="mb-1">
          <span className="text-violet-400 font-bold text-sm">
            🃏 #{choice.card_number}{choice.card_name ? ` — ${choice.card_name}` : ''}
          </span>
        </div>
        <h2 className="text-white font-semibold text-base mb-4">
          {titles[choice_type] ?? choice_type}
        </h2>

        <div className="flex-1 overflow-y-auto min-h-0">

          {/* discard_specific_cards: scegli N carte dalla mano */}
          {choice_type === 'discard_specific_cards' && (
            <div className="flex flex-wrap gap-2">
              {hand.map(c => (
                <SelectableCard
                  key={c.hand_card_id}
                  name={c.name}
                  sub={c.card_type}
                  selected={selectedHcIds.has(c.hand_card_id)}
                  onClick={() => toggleHc(c.hand_card_id, count)}
                />
              ))}
              {hand.length === 0 && <p className="text-slate-600 text-xs italic">Mano vuota.</p>}
            </div>
          )}

          {/* return_card_to_deck_top: scegli 1 carta dalla mano */}
          {choice_type === 'return_card_to_deck_top' && (
            <div className="flex flex-wrap gap-2">
              {hand.map(c => (
                <SelectableCard
                  key={c.hand_card_id}
                  name={c.name}
                  sub={c.card_type}
                  selected={selectedHcIds.has(c.hand_card_id)}
                  onClick={() => { setSelectedHcIds(new Set([c.hand_card_id])) }}
                />
              ))}
            </div>
          )}

          {/* keep_one_from_drawn: tra le carte pescate, scegli 1 */}
          {choice_type === 'keep_one_from_drawn' && (
            <div className="flex flex-wrap gap-2">
              {drawnHand.map(c => (
                <SelectableCard
                  key={c.hand_card_id}
                  name={c.name}
                  sub={c.card_type}
                  selected={selectedAcId === c.card_id}
                  onClick={() => setSelectedAcId(c.card_id)}
                />
              ))}
              {drawnHand.length === 0 && <p className="text-slate-600 text-xs italic">Nessuna carta pescata trovata in mano.</p>}
            </div>
          )}

          {/* choose_cards_to_keep: tra le carte pescate, scegli fino a max_keep */}
          {choice_type === 'choose_cards_to_keep' && (
            <div className="flex flex-wrap gap-2">
              {drawnHand.map(c => (
                <SelectableCard
                  key={c.hand_card_id}
                  name={c.name}
                  sub={c.card_type}
                  selected={selectedHcIds.has(c.hand_card_id)}
                  onClick={() => toggleHc(c.hand_card_id, max_keep)}
                />
              ))}
              {drawnHand.length === 0 && <p className="text-slate-600 text-xs italic">Nessuna carta trovata.</p>}
              <p className="w-full text-slate-500 text-[10px] mt-1">
                Selezionate: {selectedHcIds.size} / {max_keep} massimo
              </p>
            </div>
          )}

          {/* recover_from_discard: scegli N carte dal discard (solo ID) */}
          {choice_type === 'recover_from_discard' && (
            <div className="flex flex-wrap gap-2">
              {(options ?? []).map(cardId => (
                <SelectableCard
                  key={cardId}
                  name={`Carta #${cardId}`}
                  selected={selectedAcIds.has(cardId)}
                  onClick={() => toggleAc(cardId, count)}
                />
              ))}
              {(!options || options.length === 0) && <p className="text-slate-600 text-xs italic">Nessuna carta nel discard.</p>}
            </div>
          )}

          {/* delete_target_addon: scegli addon del bersaglio da eliminare */}
          {choice_type === 'delete_target_addon' && (
            <div className="flex flex-wrap gap-2">
              {(target_addon_options ?? []).map(a => (
                <SelectableCard
                  key={a.player_addon_id}
                  name={a.name}
                  sub="addon bersaglio"
                  selected={selectedAddonId === a.player_addon_id}
                  onClick={() => setSelectedAddonId(a.player_addon_id)}
                />
              ))}
              {(!target_addon_options || target_addon_options.length === 0) && (
                <p className="text-slate-600 text-xs italic">Il bersaglio non ha addon.</p>
              )}
            </div>
          )}

          {/* choose_addon_to_return: scegli 1 addon */}
          {choice_type === 'choose_addon_to_return' && (
            <div className="flex flex-wrap gap-2">
              {myAddons.map(a => (
                <SelectableCard
                  key={a.player_addon_id}
                  name={a.name}
                  sub={a.addon_type}
                  selected={selectedAddonId === a.player_addon_id}
                  onClick={() => setSelectedAddonId(a.player_addon_id)}
                />
              ))}
              {myAddons.length === 0 && <p className="text-slate-600 text-xs italic">Nessun addon in tuo possesso.</p>}
            </div>
          )}

          {/* reorder_action_deck / reorder_boss_deck */}
          {(choice_type === 'reorder_action_deck' || choice_type === 'reorder_boss_deck') && (
            <ReorderList
              items={orderedList}
              label="Trascina o usa le frecce per riordinare"
              onChange={setOrderedList}
            />
          )}
        </div>

        <div className="mt-4 pt-3 border-t border-slate-800">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit()}
            className="w-full bg-violet-700 hover:bg-violet-600 disabled:bg-slate-700 disabled:text-slate-500
              border border-violet-600 disabled:border-slate-600 rounded-xl py-2 text-white disabled:text-slate-500
              font-semibold text-sm transition-colors"
          >
            Conferma scelta
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Comply Or Refuse Modal (carta 115 — HTTP Connector) ─────────────────────

export function ComplyOrRefuseModal({
  cor,
  onComply,
  onRefuse,
}: {
  cor: ComplyOrRefuse
  onComply: () => void
  onRefuse: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border-2 border-amber-500/70 rounded-2xl p-5 shadow-2xl w-full max-w-sm flex flex-col gap-4">
        <div className="text-amber-400 font-bold text-sm">🔔 HTTP Connector — Richiesta licenza</div>
        <p className="text-slate-300 text-sm leading-relaxed">
          Un avversario ti chiede <span className="text-yellow-300 font-bold">{cor.comply_cost}L</span>.
          Se rifiuti, perdi <span className="text-red-400 font-bold">{cor.refuse_cost}L</span>.
        </p>
        <div className="flex flex-col gap-2">
          <button
            onClick={onComply}
            className="w-full bg-emerald-700 hover:bg-emerald-600 border border-emerald-500 rounded-xl py-2.5
              text-white font-semibold text-sm transition-colors"
          >
            ✓ Accetta — paga {cor.comply_cost}L
          </button>
          <button
            onClick={onRefuse}
            className="w-full bg-red-900/60 hover:bg-red-800/80 border border-red-700 rounded-xl py-2.5
              text-red-200 font-semibold text-sm transition-colors"
          >
            ✗ Rifiuta — perdi {cor.refuse_cost}L
          </button>
        </div>
      </div>
    </div>
  )
}


// ─── DebugModeModal ───────────────────────────────────────────────────────────

export function DebugModeModal({ peek, onFight, onSendBack }: {
  peek: DebugModePeek
  onFight: () => void
  onSendBack: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border-2 border-cyan-700/70 rounded-2xl p-5 shadow-2xl w-full max-w-sm flex flex-col gap-4">
        <div className="text-cyan-400 font-bold text-sm">🔍 Debug Mode — Boss in cima al mazzo</div>
        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-4 flex flex-col gap-2">
          <div className="text-white font-bold text-base">{peek.boss_name}</div>
          <div className="flex gap-3 text-xs">
            <span className="text-red-300">❤️ {peek.boss_hp} HP</span>
            <span className="text-slate-300">🎲 {peek.boss_threshold}+</span>
            <span className="text-slate-500">{peek.boss_difficulty}</span>
          </div>
          {peek.boss_ability && (
            <p className="text-slate-300 text-xs leading-relaxed border-t border-slate-700 pt-2">
              {peek.boss_ability}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <button
            onClick={onFight}
            className="w-full bg-orange-800 hover:bg-orange-700 border border-orange-600 rounded-xl py-2.5
              text-white font-semibold text-sm transition-colors"
          >
            ⚔️ Combatti
          </button>
          <button
            onClick={onSendBack}
            className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-xl py-2.5
              text-slate-300 font-semibold text-sm transition-colors"
          >
            ↩ Rimanda in fondo al mazzo
          </button>
        </div>
      </div>
    </div>
  )
}
