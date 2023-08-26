from __future__ import annotations

import typing
from dataclasses import dataclass, asdict, InitVar

import dataclass_factory

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


@dataclass
class LocalPlayer:
    player: InitVar[Player]
    words: InitVar[list[str]]
    factory: InitVar[dataclass_factory.Factory]
    results_factory: InitVar[dataclass_factory.Factory]

    id: int = None
    displayed_name: str = None
    score: int = 0
    speed: float = 0
    time_left: float = None
    is_ready: bool = False
    is_finished: bool = False
    is_out: bool = False
    team_name: str = None
    correct_words: int = 0
    incorrect_words: int = 0
    mistake_ratio: float = 0.0
    is_winner: bool = None

    def __post_init__(self, player: Player,
                      words: list[str], factory, results_factory):
        self.db_record = player
        self.id = player.pk
        self.displayed_name = player.displayed_name
        self.old_displayed_name = None
        self.total_word_length = 0
        self.voted_for = None
        self._next_word = iter(words)
        self._factory = factory
        self._results_factory = results_factory

    def get_next_word(self) -> str:
        return next(self._next_word)

    def to_dict(self, include_results=False):
        # TODO: add tests for to_dict with results
        factory = self._results_factory if include_results else self._factory
        return factory.dump(self)


@dataclass(init=False)
class LocalTeam:
    players: list
    score: int
    speed: float
    is_finished: bool
    is_out: bool
    time_left: float = None

    def __init__(self):
        self._players = dict()

    def add_player(self, player: LocalPlayer):
        self._players[player.id] = player

    def remove_player(self, player: LocalPlayer):
        self._players.pop(player.id)

    @property
    def players(self):
        return list(self._players.values())

    @property
    def score(self):
        return sum(p.score for p in self.players)

    @property
    def speed(self):
        player_count = len(self.players)
        if player_count:
            return sum(p.speed for p in self.players) / player_count

    @property
    def is_finished(self):
        return all(p.is_finished for p in self.players)

    @property
    def is_out(self):
        return all(p.is_out for p in self.players)

    @is_out.setter
    def is_out(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError('`is_out` is expected to be boolean')
        for p in self.players:
            p.is_out = value

    @property
    def is_winner(self) -> bool:
        # TODO: test it
        return any(p.is_winner for p in self.players)

    @is_winner.setter
    def is_winner(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError('`is_winner` is expected to be boolean')
        for p in self.players:
            p.is_winner = value


@dataclass
class GameOptions:
    WIN_CONDITION_BEST_SCORE = 'PointsCompetition'
    WIN_CONDITION_BEST_TIME = 'Race'
    WIN_CONDITION_SURVIVED = 'Survival'

    game_duration: int = 60
    win_condition: str = WIN_CONDITION_BEST_SCORE
    team_mode: bool = False
    speed_up_percent: float = 0.0
    points_difference: int = 0
    time_per_word: float = 0.0
    strict_mode: bool = False
    start_delay: float = 0.0


# FIXME: get rid of this hack by updating every workstation python ver to 3.10
# Issue discussed at --
# https://stackoverflow.com/questions/70400639/
# /how-do-i-get-python-dataclass-initvar-fields-to-work-with-typing-get-type-hints
InitVar.__call__ = lambda *args: None
