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
