"""
WebSocket event types sent between server and clients.
"""


class ClientAction:
    """Actions sent from client to server."""
    JOIN_GAME = "join_game"
    SELECT_CHARACTER = "select_character"
    START_GAME = "start_game"
    DRAW_CARD = "draw_card"
    PLAY_CARD = "play_card"
    BUY_ADDON = "buy_addon"
    USE_ADDON = "use_addon"
    START_COMBAT = "start_combat"
    ROLL_DICE = "roll_dice"
    END_TURN = "end_turn"
    RETREAT_COMBAT = "retreat_combat"
    DECLARE_CARD = "declare_card"           # boss 33 — declare card before rolling
    DECLARE_CARD_TYPE = "declare_card_type" # boss 86 — declare Offensiva/Difensiva at combat start
    PLAY_REACTION = "play_reaction"         # out-of-turn: {hand_card_id: int}
    PASS_REACTION = "pass_reaction"         # out-of-turn: pass the reaction window
    STACK_PASS = "stack_pass"
    STACK_PLAY_CARD = "stack_play_card"
    # Role passive actions
    ROLE_DISCARD_DRAW = "role_discard_draw"              # Administrator / Advanced Admin
    ROLE_RECOVER_FROM_DISCARD = "role_recover_from_discard"  # Integration Architect
    ROLE_SKIP_DRAW = "role_skip_draw"                    # Marketing Cloud Administrator
    ROLE_PREDICT_ROLL = "role_predict_roll"              # Einstein Analytics Consultant
    BOSS_PEEK_CHOICE = "boss_peek_choice"                # Data Architect
    DRAW_PEEK_CHOICE = "draw_peek_choice"                # Data Cloud Consultant


class ServerEvent:
    """Events sent from server to clients."""
    GAME_STATE = "game_state"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTED = "game_started"
    TURN_STARTED = "turn_started"
    CARD_DRAWN = "card_drawn"
    CARD_PLAYED = "card_played"
    ADDON_BOUGHT = "addon_bought"
    ADDON_USED = "addon_used"
    COMBAT_STARTED = "combat_started"
    DICE_ROLLED = "dice_rolled"
    COMBAT_ENDED = "combat_ended"
    PLAYER_DIED = "player_died"
    TURN_ENDED = "turn_ended"
    GAME_OVER = "game_over"
    HAND_STATE = "hand_state"
    ERROR = "error"
    REACTION_WINDOW_OPEN = "reaction_window_open"   # privato al target: puoi reagire
    REACTION_WINDOW_CLOSED = "reaction_window_closed" # privato al target: finestra chiusa
    REACTION_RESOLVED = "reaction_resolved"           # broadcast: come è andata la reazione
    LUCKY_ROLL_USED = "lucky_roll_used"               # broadcast: combatant ha usato Lucky Roll
    STACK_OPENED = "stack_opened"
    STACK_PRIORITY = "stack_priority"
    STACK_UPDATED = "stack_updated"
    STACK_PASSED = "stack_passed"
    STACK_RESOLVED = "stack_resolved"
    # Role passive server events
    BOSS_PEEK_CHOICE_REQUIRED = "boss_peek_choice_required"    # private to Data Architect
    DRAW_PEEK_CHOICE_REQUIRED = "draw_peek_choice_required"    # private to Data Cloud Consultant
    EINSTEIN_PREDICTION_CORRECT = "einstein_prediction_correct"
    ROLE_PREDICT_ROLL_ANNOUNCED = "role_predict_roll_announced"
    ROLE_DISCARD_DRAW = "role_discard_draw"
    ROLE_RECOVER_FROM_DISCARD = "role_recover_from_discard"
    ROLE_SKIP_DRAW = "role_skip_draw"
