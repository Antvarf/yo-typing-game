from dataclasses import dataclass, InitVar

import dataclass_factory

from base.models import Player


# naming style used on client for easy converting
NAME_STYLE = dataclass_factory.NameStyle.camel_lower


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
        if type(value) is not bool:
            raise TypeError('`is_out` is expected to be boolean')
        for p in self.players:
            p.is_out = value

    @property
    def is_winner(self) -> bool:
        # TODO: test it
        return any(p.is_winner for p in self.players)

    @is_winner.setter
    def is_winner(self, value: bool):
        if type(value) is not bool:
            raise TypeError('`is_winner` is expected to be boolean')
        for p in self.players:
            p.is_winner = value
