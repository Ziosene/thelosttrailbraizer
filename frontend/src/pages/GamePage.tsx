import { useEffect, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { useAuthStore } from '../store/authStore'

function LogoutButton() {
  const { logout } = useAuthStore()
  return (
    <button
      onClick={logout}
      className="text-[10px] text-slate-500 hover:text-red-400 border border-slate-700 hover:border-red-700 rounded px-2 py-1 transition-colors"
    >
      Esci
    </button>
  )
}
import { CardOverlay } from '../components/game/CardVisual'
import type { CardInfo } from '../components/game/CardVisual'
import { PlayArea } from '../components/game/PlayArea'
import type { CellData } from '../components/game/PlayArea'
import type { Corner } from '../components/game/PlayerCell'
import { HandPanel } from '../components/game/HandPanel'
import { LogPanel } from '../components/game/LogPanel'
import { ReactionWindowModal, CardChoiceModal, ComplyOrRefuseModal, DebugModeModal } from '../components/game/GameModals'
import { ToastLayer } from '../components/game/ToastLayer'
import { CombatOverlay } from '../components/game/CombatOverlay'

interface GamePageProps {
  gameCode: string
}

export function GamePage({ gameCode }: GamePageProps) {
  const { user } = useAuthStore()
  const {
    gameState, hand, myAddons, pendingChoice, reactionWindow, complyOrRefuse, debugModePeek, log,
    lastDiceRoll, connect, disconnect, send, clearPendingChoice,
  } = useGameStore()
  const [logOpen, setLogOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<CardInfo | null>(null)

  useEffect(() => {
    if (user) connect(gameCode, user.id)
    return () => { disconnect() }
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
    rows = [[{ p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'bottom-full' as Corner }]]
  } else if (nPlayers === 2) {
    rows = [
      [{ p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'top-full' as Corner }],
      [{ p: rotated[1], isMe: rotated[1].user_id === myUserId, corner: 'bottom-full' as Corner }],
    ]
  } else if (nPlayers === 3) {
    rows = [
      [
        { p: rotated[0], isMe: rotated[0].user_id === myUserId, corner: 'top-left' as Corner },
        { p: rotated[1], isMe: rotated[1].user_id === myUserId, corner: 'top-right' as Corner },
      ],
      [{ p: rotated[2], isMe: rotated[2].user_id === myUserId, corner: 'bottom-full' as Corner }],
    ]
  } else {
    const topRow: CellData[] = rotated.slice(0, nPlayers - 2).map((p, i) => ({
      p,
      isMe: p.user_id === myUserId,
      corner: (i % 2 === 0 ? 'top-left' : 'top-right') as Corner,
    }))
    rows = [
      topRow,
      [
        { p: rotated[nPlayers - 2], isMe: rotated[nPlayers - 2].user_id === myUserId, corner: 'bottom-left' as Corner },
        { p: rotated[nPlayers - 1], isMe: rotated[nPlayers - 1].user_id === myUserId, corner: 'bottom-right' as Corner },
      ],
    ]
  }

  const currentPlayer = gameState.players.find(p => p.id === gameState.current_player_id)
  const turnLabel = isMyTurn
    ? '→ Tu'
    : currentPlayer ? `→ ${currentPlayer.nickname}` : ''

  const PHASE_LABELS: Record<string, string> = {
    draw:   '🃏 Pesca',
    action: '⚡ Azione',
    combat: '⚔️ Combattimento',
    end:    '✓ Fine turno',
  }

  return (
    <div className="h-screen bg-slate-950 flex flex-col text-slate-200 text-sm overflow-hidden select-none">

      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center gap-3 text-xs shrink-0 flex-wrap">
        <span className="text-violet-400 font-bold">The Lost Trailbraizer</span>
        <span className="text-slate-700">|</span>
        <span className="text-slate-400">
          Turno <span className="text-white font-semibold">{gameState.turn_number}</span>
        </span>
        {gameState.current_phase && (
          <span className={`px-2 py-0.5 rounded-full font-semibold text-[10px]
            ${isMyTurn && gameState.current_phase === 'draw'
              ? 'bg-amber-500/80 text-amber-100 animate-pulse'
              : 'bg-slate-700/80 text-slate-300'}`}>
            {PHASE_LABELS[gameState.current_phase] ?? gameState.current_phase}
          </span>
        )}
        {turnLabel && (
          <span className={isMyTurn ? 'text-violet-300 font-semibold' : 'text-slate-300 font-semibold'}>
            {turnLabel}
          </span>
        )}
        <span className="text-slate-600 text-[10px]">#{gameCode}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setLogOpen(v => !v)}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-1 text-slate-300 transition-colors"
          >
            📋 Log
          </button>
          <LogoutButton />
        </div>
      </div>

      {/* Griglia giocatori + market */}
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
      />

      {/* Mano + Mazzi */}
      <HandPanel
        hand={hand}
        gameState={gameState}
        isMyTurn={isMyTurn}
        onCardClick={setSelectedCard}
        onPlayCard={(id) => send('play_card', { hand_card_id: id })}
        onDrawCard={(deck) => send('draw_card', { deck })}
      />

      {logOpen && <LogPanel entries={log} onClose={() => setLogOpen(false)} />}
      {selectedCard && <CardOverlay card={selectedCard} onClose={() => setSelectedCard(null)} />}
      <ToastLayer />

      {/* Combat overlay — shown when the current user is in combat */}
      {myPlayer?.is_in_combat && myPlayer.current_boss && (
        <CombatOverlay
          boss={myPlayer.current_boss}
          bossHp={myPlayer.current_boss_hp ?? myPlayer.current_boss.hp}
          playerHp={myPlayer.hp}
          playerMaxHp={myPlayer.max_hp}
          combatRound={myPlayer.combat_round ?? 0}
          hand={hand}
          addons={myAddons}
          lastDiceRoll={lastDiceRoll}
          isMyTurn={isMyTurn}
          onRollDice={() => send('roll_dice')}
          onPlayCard={(id) => send('play_card', { hand_card_id: id })}
          onUseAddon={(id) => send('use_addon', { player_addon_id: id })}
          onRetreat={() => send('retreat_combat')}
        />
      )}

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

      {debugModePeek && (
        <DebugModeModal
          peek={debugModePeek}
          onFight={() => {
            send('debug_mode_choice', { decision: 'fight' })
            useGameStore.setState({ debugModePeek: null })
          }}
          onSendBack={() => {
            send('debug_mode_choice', { decision: 'send_back' })
            useGameStore.setState({ debugModePeek: null })
          }}
        />
      )}

      {complyOrRefuse && (
        <ComplyOrRefuseModal
          cor={complyOrRefuse}
          onComply={() => {
            send('pass_reaction')
            useGameStore.setState({ complyOrRefuse: null })
          }}
          onRefuse={() => {
            send('card115_refuse')
            useGameStore.setState({ complyOrRefuse: null })
          }}
        />
      )}
    </div>
  )
}
