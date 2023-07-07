from __future__ import annotations

import random
import secrets
from collections import Counter
from dataclasses import dataclass, asdict, InitVar
import typing
from functools import cached_property

import dataclass_factory
from django.utils import timezone

from base import helpers
from base.models import (
    GameSession,
    GameModes,
    Player,
)


# naming style used on client for easy converting
NAME_STYLE = dataclass_factory.NameStyle.camel_lower


class ControllerStorage:
    _sessions = dict()

    def get_game_controller(self, controller_cls, session_id: str):
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                'use_count': 0,
                'controller': controller_cls(session_id),
            }
        self._sessions[session_id]['use_count'] += 1
        controller = self._sessions[session_id]['controller']
        return controller

    def remove_game_controller(self, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id]['use_count'] -= 1
            if self._sessions[session_id]['use_count'] <= 0:
                self._sessions.pop(session_id)


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


class ControllerError(Exception):
    pass


class PlayerJoinRefusedError(ControllerError):
    pass


class EventTypeNotDefinedError(ControllerError):
    pass


class GameOverError(ControllerError):
    pass


class InvalidMessageError(ControllerError):
    pass


class ControllerExistsError(ControllerError):
    pass


class InvalidGameStateError(ControllerError):
    pass


class InvalidModeChoiceError(ControllerError):
    pass


class InvalidOperationError(ControllerError):
    pass


class WordListProvider:
    def __init__(self):
        self._words = []
        self._extend_word_list()

    def _extend_word_list(self):
        word_page = self._get_new_word_page()
        self._words.extend(word_page)
        self._new_word_iterator = iter(word_page)

    @staticmethod
    def _get_new_word_page(n: int = 100) -> list[str]:
        word_page = helpers.get_words(n)
        return word_page

    @property
    def words(self) -> list[str]:
        if not self._words:
            self._extend_word_list()
        return self._words

    def get_new_word(self) -> str:
        word = next(self._new_word_iterator, None)
        if word is None:
            self._extend_word_list()
            word = next(self._new_word_iterator)
        return word


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


@dataclass
class GameOptions:
    WIN_CONDITION_BEST_SCORE = 'PointsCompetition'
    WIN_CONDITION_BEST_TIME = 'Race'
    WIN_CONDITION_SURVIVED = 'Survival'

    game_duration: int = 60
    win_condition: str = WIN_CONDITION_BEST_SCORE
    team_mode: bool = False
    # TODO: test defaults here
    speed_up_percent: float = 100.0
    points_difference: int = 0
    time_per_word: float = 0.0
    strict_mode: bool = False
    start_delay: float = 0.0


def updates_db(f):
    def wrapper(self, *args, **kwargs):
        result = f(self, *args, **kwargs)
        self._perform_database_update()
        return result
    return wrapper


@dataclass(init=False)
class PlayerController:
    players: list[LocalPlayer]
    teams: dict[str, LocalTeam]

    def __init__(self, session: GameSession, words: list[str],
                 options: GameOptions = GameOptions()):
        self.session = session
        self.ready_count = 0
        self.voted_count = 0
        self._displayed_names = set()
        self._players = dict()
        self._options = options
        if self._options.team_mode:
            self.teams = dict()
            self.team_red = self.teams['red'] = LocalTeam()
            self.team_blue = self.teams['blue'] = LocalTeam()
        self._factory = self._get_dataclass_factory()
        self._results_factory = self._get_dataclass_factory(
            add_extra_stats=True,
        )
        self._unique_displayed_names = set()
        self._words = words

    def _get_dataclass_factory(self, add_extra_stats=False):
        self_fields_included = []
        player_fields_included = ['id', 'displayed_name',
                                  'score', 'speed', 'is_ready']
        team_fields_included = ['players', 'score', 'speed']

        if self._options.team_mode:
            self_fields_included.append('teams')
            player_fields_included.append('team_name')
            if self._options.game_duration:
                team_fields_included.append('time_left')
        else:
            self_fields_included.append('players')
            if self._options.game_duration:
                player_fields_included.append('time_left')

        if self._options.win_condition == GameOptions.WIN_CONDITION_SURVIVED:
            player_fields_included.append('is_out')
            team_fields_included.append('is_out')

        if add_extra_stats:
            player_fields_included.extend([
                'correct_words',
                'incorrect_words',
                'mistake_ratio',
                'is_winner',
            ])

        self_schema = dataclass_factory.Schema(only=self_fields_included,
                                               name_style=NAME_STYLE)
        player_schema = dataclass_factory.Schema(only=player_fields_included,
                                                 name_style=NAME_STYLE)
        team_schema = dataclass_factory.Schema(only=team_fields_included,
                                               name_style=NAME_STYLE)

        # TODO: add is_finished param
        return dataclass_factory.Factory(
            schemas={
                PlayerController: self_schema,
                LocalPlayer: player_schema,
                LocalTeam: team_schema,
            },
        )

    @property
    def players(self) -> list[LocalPlayer]:
        return list(self._players.values())

    @property
    def player_count(self) -> int:
        return len(self._players)

    @property
    def votes(self):
        _votes = Counter([p.voted_for
                          for p in self._players.values() if p.voted_for])
        return _votes

    @updates_db
    def add_player(self, player: Player) -> LocalPlayer:
        if player.pk in self._players:
            return self.get_player(player)
        if self.session.players_max \
           and self.player_count >= self.session.players_max:
            raise PlayerJoinRefusedError('Max players limit was reached')

        local_player = self._init_local_player(player, self._words)
        self._add_to_unique_displayed_names(local_player)
        self._players[player.pk] = local_player

        if self._options.team_mode:
            if len(self.team_red.players) <= len(self.team_blue.players):
                local_player.team_name = 'red'
                team = self.team_red
            else:
                local_player.team_name = 'blue'
                team = self.team_blue
            team.add_player(local_player)

        return local_player

    def get_player(self, player: Player = None) -> LocalPlayer | None:
        # TODO: test empty player argument
        local_player = None
        if player is not None:
            local_player = self._players[player.pk]
        elif self._players.values():
            local_player = random.choice(list(self._players.values()))
        return local_player

    @updates_db
    def remove_player(self, player: Player):
        local_player = self._players.pop(player.pk)
        if local_player.is_ready:
            self.ready_count -= 1
        if local_player.voted_for is not None:
            self.voted_count -= 1
        self._remove_from_unique_displayed_names(local_player)

        if self._options.team_mode:
            team = self.teams[local_player.team_name]
            team.remove_player(local_player)

    def set_ready_state(self, player: Player, state: bool):
        local_player = self.get_player(player)
        if local_player.is_ready != state:
            self.ready_count += 1 if state else -1
            local_player.is_ready = state

    def set_player_vote(self, player: Player, vote: str):
        if vote not in GameModes.labels:
            raise InvalidModeChoiceError(f'Cannot select mode `{vote}`')
        local_player = self.get_player(player)
        if local_player.voted_for is None:
            self.voted_count += 1
            local_player.voted_for = vote

    def set_player_team(self, player: Player, team: str):
        if not self._options.team_mode:
            raise InvalidOperationError

        team_obj = self.teams[team]
        local_player = self.get_player(player)
        player_team = self.teams[local_player.team_name]

        if local_player not in team_obj.players:
            player_team.remove_player(local_player)
            team_obj.add_player(local_player)
            local_player.team_name = team

    def to_dict(self, include_results=False):
        # TODO: add tests for to_dict with results
        factory = self._results_factory if include_results else self._factory
        return factory.dump(self)

    def _perform_database_update(self):
        self._update_session_record()

    def _update_session_record(self):
        self.session.players_now = self.player_count
        self.session.save()

    def save_results(self):
        # TODO: this will need a refactor
        #   1. Schema (and model) should account for other fields like is_out
        #   2. My mom said it smells bad in my room, must be this code
        schema_fields = [
            'score', 'speed', 'is_winner',
            'correct_words', 'incorrect_words', 'mistake_ratio'
        ]
        if self._options.team_mode:
            schema_fields.append('team_name')
        result_schema = dataclass_factory.Schema(
            only=schema_fields,
        )
        factory = dataclass_factory.Factory(default_schema=result_schema)

        results = []
        for player in self._players.values():
            result = factory.dump(player)
            result.update({'player': player.db_record})
            results.append(result)
        self.session.save_results(results)

    def _init_local_player(self, player: Player, words: list[str]):
        local_player = LocalPlayer(
            player,
            words=words,
            factory=self._factory,
            results_factory=self._results_factory,
        )
        return local_player

    def _add_to_unique_displayed_names(self, player: LocalPlayer):
        new_displayed_name = \
            player.old_displayed_name = player.displayed_name
        while new_displayed_name in self._unique_displayed_names:
            tag = secrets.token_urlsafe(3)
            new_displayed_name = f'{player.displayed_name}#{tag}'
        player.displayed_name = new_displayed_name
        self._unique_displayed_names.add(player.displayed_name)

    def _remove_from_unique_displayed_names(self, player: LocalPlayer):
        self._unique_displayed_names.remove(player.displayed_name)
        player.displayed_name = player.old_displayed_name


class GameController:
    STATE_PREPARING = 'preparing'
    STATE_PLAYING = 'playing'
    STATE_VOTING = 'voting'

    word_provider_class = WordListProvider
    player_controller_class = PlayerController

    def __init__(self, session_id=None):
        self._session = GameSession.objects.get(session_id=session_id)
        if self._session.started_at or self._session.is_finished:
            raise GameOverError

        self._state = self.STATE_PREPARING
        self._options = self._init_options()
        self._word_provider = self.word_provider_class()
        self._player_controller = self.player_controller_class(
            session=self._session,
            options=self._options,
            words=self._word_provider.words,
        )
        self._event_handlers = self._init_event_handlers()
        self._modes_available = GameModes.labels
        self._game_begins_at = None
        self._last_tick = None

        self._host_id = None

    def player_event(self, event: Event) -> list[Event]:
        if type(event) is not Event:
            raise TypeError('`event` is expected to be of type `Event`')
        if not event.is_valid():
            raise InvalidMessageError
        handler = self._get_event_handler(event.type)
        events = handler(**event.data.to_dict())
        return events

    @property
    def host_id(self) -> int:
        return self._host_id

    def set_host(self, new_host: Player):
        if type(new_host) is not Player:
            raise TypeError('host should be of type `Player`')
        if not self._player_exists(new_host):
            raise ValueError(f'player {new_host} is not in session')
        self._host_id = new_host.pk

    def _init_event_handlers(self):
        event_handlers = {
            Event.PLAYER_JOINED: self._handle_player_join,
            Event.PLAYER_LEFT: self._handle_player_leave,
            Event.PLAYER_READY_STATE: self._handle_player_ready,
            Event.PLAYER_WORD: self._handle_word,
            Event.TRIGGER_TICK: self._handle_tick,
            Event.PLAYER_MODE_VOTE: self._handle_player_vote,
            Event.PLAYER_SWITCH_TEAM: self._handle_switch_team,
        }
        if hasattr(self, 'get_extending_event_handlers'):
            extensions = self.get_extending_event_handlers()
            event_handlers.update(extensions)  # Allow event handler override
        return event_handlers

    def _get_event_handler(self, event: str):
        try:
            return self._event_handlers[event]
        except KeyError:
            raise EventTypeNotDefinedError

    ### Event handlers start here ###

    def _handle_player_join(self, player: Player, payload={}) -> list[Event]:
        """
        Event handler for player joining the session.
        """
        events = []
        if self._can_player_join(player, **payload):
            player_obj = self._add_player(player)
            events.append(self._get_initial_state_event(player_obj))
            events.append(self._get_players_update_event())
            return events
        raise PlayerJoinRefusedError

    def _handle_player_leave(self, player: Player) -> list[Event]:
        """Event handler for player leaving the session"""
        events = []
        if self._player_exists(player):
            self._remove_player(player)
            if self._is_host(player):
                events.append(self._set_new_host())
            events.append(self._get_players_update_event())
            if self._can_start():
                game_begins_event = self._get_game_begins_event()
                events.append(game_begins_event)
                if self._options.start_delay <= 0:
                    start_game_event = self._start_game()
                    events.append(start_game_event)
                else:
                    self._stage_start_game(self._options.start_delay)
            if not self._player_count and self._state is self.STATE_PLAYING:
                events.append(self._game_over())
            if self._is_voting_finished():
                events.append(self._create_new_game())
        return events

    def _handle_player_ready(self,
                             player: Player,
                             payload: bool,
                             ) -> list[Event]:
        events = []
        if not self._player_exists(player):
            return []
        if self._state is self.STATE_PREPARING:
            self._set_ready_state(player, payload)
            events.append(self._get_players_update_event())
            if self._can_start():
                game_begins_event = self._get_game_begins_event()
                events.append(game_begins_event)
                if self._options.start_delay <= 0:
                    start_game_event = self._start_game()
                    events.append(start_game_event)
                else:
                    self._stage_start_game(self._options.start_delay)
        return events

    def _handle_word(self, player: Player, payload: str) -> list[Event]:
        events = []
        if self._state is self.STATE_PLAYING:
            local_player = self._player_controller.get_player(player)
            if payload == local_player.get_next_word():
                word_length = len(payload)
                local_player.score += word_length
                local_player.total_word_length += word_length
                eta = (timezone.now() - self._session.started_at).total_seconds()
                local_player.speed = local_player.total_word_length / eta
                local_player.correct_words += 1
                if self._options.time_per_word:
                    bonus_time = self._options.time_per_word * word_length
                    if self._options.team_mode:
                        competitor = self._player_controller.teams[local_player.team_name]
                    else:
                        competitor = local_player
                    competitor.time_left = min(
                        float(self._options.game_duration),
                        competitor.time_left + bonus_time,
                    )
            else:
                # TODO: cover with tests
                local_player.incorrect_words += 1
            # TODO: check for game_over condition
            events.append(self._get_new_word_event())
            events.append(self._get_players_update_event())
        return events

    def _handle_tick(self, player, **kwargs) -> list[Event]:
        events = []
        if not self._is_host(player):
            pass

        elif self._state is self.STATE_PREPARING:
            if self._game_begins_at is not None:
                if timezone.now() >= self._game_begins_at:
                    events.append(self._start_game())

        elif self._state is self.STATE_PLAYING:
            if self._options.game_duration:
                prev_tick = self._last_tick or self._session.started_at
                self._last_tick = timezone.now()
                time_delta = self._last_tick - prev_tick

                for c in self._competitors:
                    # TODO: implement speed_up_percent setting
                    c.time_left -= time_delta.total_seconds()
                    is_survival = self._options.win_condition \
                        == GameOptions.WIN_CONDITION_SURVIVED
                    if is_survival and c.time_left <= 0:
                        c.time_left = 0
                        c.is_out = True

            events.append(self._get_players_update_event())

            if self._is_game_over():
                events.append(self._game_over())

        elif self._state is self.STATE_VOTING:
            pass
        return events

    def _handle_player_vote(self, player: Player, payload: str) -> list[Event]:
        events = []
        if self._state is self.STATE_VOTING:
            if payload in self._modes_available:
                self._set_player_vote(player, payload)
                events.append(self._get_votes_update_event())
            else:
                events.append(self._get_modes_available_event())

            if self._is_voting_finished():
                events.append(self._create_new_game())
        return events

    def _handle_switch_team(self, player: Player, payload: str) -> list[Event]:
        events = []
        if self._state is not self.STATE_PREPARING:
            raise InvalidOperationError
        self._player_controller.set_player_team(player, payload)
        events.append(self._get_players_update_event())
        return events

    def _get_initial_state_event(self, player: LocalPlayer) -> Event:
        event = Event(
            target=Event.TARGET_PLAYER,
            type=Event.SERVER_INITIAL_STATE,
            data={
                'player': player.to_dict(),
                'words': self._word_provider.words,
                **self._competitors_field,
            }
        )
        return event

    def _get_players_update_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_PLAYERS_UPDATE,
                      data=self._competitors_field)
        return event

    def _get_game_begins_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_GAME_BEGINS,
                      data=self._options.start_delay)
        return event

    def _get_new_word_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_NEW_WORD,
                      data=self._word_provider.get_new_word())
        return event

    def _get_votes_update_event(self) -> Event:
        mode_votes = [
            {
                'mode': mode,
                'voteCount': self._player_controller.votes.get(mode, 0),
            }
            for mode
            in GameModes.labels
        ]
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_VOTES_UPDATE, data=mode_votes)
        return event

    def _get_modes_available_event(self) -> Event:
        event = Event(target=Event.TARGET_PLAYER,
                      type=Event.SERVER_MODES_AVAILABLE,
                      data=self._modes_available)
        return event

    def _get_new_game_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_NEW_GAME,
                      data=self._new_session_id)
        return event

    def _init_options(self) -> GameOptions:
        options = GameOptions()
        if self._session.mode == GameModes.SINGLE:
            pass
        elif self._session.mode == GameModes.IRONWALL:
            options.strict_mode = True
        elif self._session.mode == GameModes.ENDLESS:
            options.game_duration = 30
            options.win_condition = GameOptions.WIN_CONDITION_SURVIVED
            options.time_per_word = 0.5
            options.speed_up_percent = 140.0
        elif self._session.mode == GameModes.TUGOFWAR:
            options.game_duration = 0
            options.team_mode = True
            options.points_difference = 50
        if self._session.players_max != 1:
            options.start_delay = 3
        return options

    def _add_player(self, player: Player) -> LocalPlayer:
        local_player = self._player_controller.add_player(player)
        return local_player

    def _remove_player(self, player: Player):
        self._player_controller.remove_player(player)

    def _get_player(self, player: Player) -> LocalPlayer:
        return self._player_controller.get_player(player)

    @property
    def _competitors_field(self) -> dict:
        return self._player_controller.to_dict()

    @property
    def _players_with_results(self) -> list[dict]:
        serialized = self._player_controller.to_dict(include_results=True)
        if self._options.team_mode:
            teams = serialized['teams']
            players = [player
                       for team in teams.values()
                       for player in team['players']]
        else:
            players = serialized['players']
        return players

    @property
    def _competitors(self):
        if self._options.team_mode:
            competitors = list(self._player_controller.teams.values())
        else:
            competitors = self._player_controller.players
        return competitors

    def _can_start(self) -> bool:
        if self._state is not self.STATE_PREPARING:
            return False
        players_ready = self._player_controller.ready_count
        players_count = self._player_controller.player_count
        return players_count and players_ready >= players_count

    def _is_voting_finished(self) -> bool:
        if self._state is not self.STATE_VOTING:
            return False
        players_voted = self._player_controller.voted_count
        players_count = self._player_controller.player_count
        return players_count and players_voted >= players_count

    def _can_player_join(self, player: Player, password: str = None) -> bool:
        if 0 < self._session.players_max <= self._player_count:
            return False
        if self._state is not self.STATE_PREPARING:
            return False
        if self._player_exists(player):
            return False
        if self._session.password \
                and not self._session.check_password(password):
            return False
        return True

    def _player_exists(self, player: Player) -> bool:
        """
        Checks if player with given player record is present in the session
        """
        try:
            self._get_player(player)
        except KeyError:
            return False
        else:
            return True

    def _is_host(self, player: Player):
        if self._host_id is None:
            return False
        return self._host_id == player.pk

    def _set_new_host(self) -> Event:
        new_host = self._player_controller.get_player()
        self._host_id = new_host and new_host.id
        event = Event(type=Event.SERVER_NEW_HOST,
                      target=Event.TARGET_ALL, data=self.host_id)
        return event

    def _set_ready_state(self, player: Player, state: bool):
        self._player_controller.set_ready_state(player, state)

    def _set_player_vote(self, player: Player, mode: str):
        self._player_controller.set_player_vote(player, mode)

    @property
    def _player_count(self) -> int:
        return self._player_controller.player_count

    def _stage_start_game(self, countdown: float):
        """
        Set _game_begins_at for future ticks to compare tz.now() against
        """
        offset = timezone.timedelta(seconds=countdown)
        self._game_begins_at = timezone.now() + offset

    def _start_game(self) -> Event:
        """
        Updates controller and database record state to STATE_PLAYING.

        NOTE: this function is used heavily in unit tests to alter game state.
        """
        self._state = self.STATE_PLAYING
        self._session.start_game()

        self._post_start()

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_START_GAME, data={})
        return event

    def _post_start(self):
        if self._options.game_duration:
            game_duration = self._options.game_duration
            offset = timezone.timedelta(seconds=game_duration)
            self._game_ends_at = self._session.started_at + offset
            if self._options.team_mode:
                for t in self._player_controller.teams.values():
                    t.time_left = game_duration
            else:
                for p in self._player_controller.players:
                    p.time_left = game_duration

        if self._options.points_difference:
            # TODO: can't start with less than two competitors
            pass

    def _game_over(self) -> Event:
        """
        Updates controller and database record state to STATE_VOTING.

        NOTE: this function is used heavily in unit tests to alter game state.
        """
        self._state = self.STATE_VOTING
        self._session.game_over()
        self._mark_winners()
        # TODO: test that results are actually saved -> test game_over
        self._player_controller.save_results()

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_GAME_OVER, data=self.results)
        return event

    def _mark_winners(self):
        if not self._competitors:
            return
        if self._options.win_condition == GameOptions.WIN_CONDITION_BEST_SCORE:
            max_score = max(c.score for c in self._competitors)
            for competitor in self._competitors:
                if competitor.score == max_score:
                    competitor.is_winner = True
                else:
                    competitor.is_winner = False
        if self._options.win_condition == GameOptions.WIN_CONDITION_BEST_TIME:
            max_time_left = max(c.time_left for c in self._competitors)
            for competitor in self._competitors:
                if competitor.time_left == max_time_left:
                    competitor.is_winner = True
                else:
                    competitor.is_winner = False
        if self._options.win_condition == GameOptions.WIN_CONDITION_SURVIVED:
            for competitor in self._competitors:
                competitor.is_winner = not competitor.is_out

        if len(self._competitors) == 1:
            self._competitors[0].is_winner = True
        # TODO: cover with tests

    @cached_property
    def results(self) -> list[dict]:
        return self._players_with_results

    def _is_game_over(self) -> bool:
        if self._options.win_condition == GameOptions.WIN_CONDITION_SURVIVED:
            out_count = [c.is_out for c in self._competitors].count(True) # TODO: move count to player controller
            return out_count and out_count >= len(self._competitors) - 1

        if self._options.game_duration:
            if self._game_ends_at <= timezone.now():
                return True

        if self._options.points_difference:
            scores = set(c.score for c in self._competitors)
            if scores:
                top_score = max(scores)
                scores.remove(top_score)
            if scores:
                second_top_score = max(scores)
                points_difference = top_score - second_top_score
                if points_difference >= self._options.points_difference:
                    return True
                # TODO: test for the case when one competitor remains
        return False

    def _create_new_game(self) -> Event:
        """A function that creates a game with the same settings as current"""
        # TODO: refactor this list comprehension hell
        most_common = self._player_controller.votes.most_common()
        max_count = most_common[0][1]
        new_mode = random.choices([
            mode for mode, count in most_common
            if count == max_count
        ])[0]
        new_mode_value = {k: v for v, k in GameModes.choices}[new_mode]
        new_session = self._session.create_from_previous(
            new_mode=new_mode_value,
        )
        self._new_session_id = str(new_session.session_id)
        self._state = None
        event = self._get_new_game_event()
        return event


# FIXME: get rid of this hack by updating every workstation python ver to 3.10
# Issue discussed at --
# https://stackoverflow.com/questions/70400639/
# /how-do-i-get-python-dataclass-initvar-fields-to-work-with-typing-get-type-hints
InitVar.__call__ = lambda *args: None
