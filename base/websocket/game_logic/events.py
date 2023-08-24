import typing
from dataclasses import dataclass, asdict

from base.models import Player


@dataclass
class PlayerMessage:
    player: Player = None
    payload: typing.Any = None

    def to_dict(self):
        data = asdict(self)
        if self.payload is None:
            data.pop('payload')
        return data


@dataclass
class Event:
    PLAYER_JOINED = 'player_joined'
    PLAYER_LEFT = 'player_left'
    PLAYER_READY_STATE = 'ready_state'
    PLAYER_WORD = 'word'
    PLAYER_MODE_VOTE = 'vote'
    PLAYER_SWITCH_TEAM = 'switch_team'

    SERVER_INITIAL_STATE = 'initial_state'
    SERVER_PLAYERS_UPDATE = 'players_update'
    SERVER_GAME_BEGINS = 'game_begins'
    SERVER_START_GAME = 'start_game'
    SERVER_NEW_WORD = 'new_word'
    SERVER_GAME_OVER = 'game_over'
    SERVER_MODES_AVAILABLE = 'modes_available'  # TODO: add event to asyncapi spec
    SERVER_VOTES_UPDATE = 'votes_update'
    SERVER_NEW_GAME = 'new_game'
    SERVER_CLOSE_CONNECTION = 'close_connection'
    SERVER_TICK = 'tick'
    SERVER_ERROR = 'error'
    # SERVER_USERNAME_SWITCH = 'username_switch'
    SERVER_NEW_HOST = 'new_host'

    TRIGGER_TICK = 'tick'

    TARGET_ALL = 'all'
    TARGET_PLAYER = 'player'

    type: str
    data: typing.Any
    target: str = None

    def is_valid(self):
        # TODO: implement validation logic
        return True

    def to_dict(self) -> dict:
        result = asdict(self)
        result.pop('target')
        return result
