from abc import ABC, abstractmethod
from dataclasses import dataclass
import typing
from functools import cached_property

from django.utils import timezone

from base import helpers
from base.models import (
    GameSession,
    GameModes,
    Player,
)


@dataclass
class PlayerMessage:
    player: Player
    payload: typing.Any = None


@dataclass
class Event:
    PLAYER_JOINED = 'player_joined'
    PLAYER_LEFT = 'player_left'
    PLAYER_READY_STATE = 'ready_state'
    PLAYER_WORD = 'word'
    PLAYER_MODE_VOTE = 'vote'
    # PLAYER_SWITCH_TEAM = 'switch_team'

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
    # SERVER_USERNAME_SWITCH = 'username_switch'

    TRIGGER_TICK = 'tick'

    TARGET_ALL = 'all'
    TARGET_PLAYER = 'player'

    type: str
    data: typing.Any
    target: str = None


class PlayerJoinRefusedError(Exception):
    pass


class EventTypeNotDefinedError(Exception):
    pass


class GameOverError(Exception):
    pass


class InvalidMessageError(Exception):
    pass


class ControllerExistsException(Exception):
    pass


class InvalidGameStateException(Exception):
    pass


class WordListProvider:
    def __init__(self):
        self._words = self._get_new_word_page()

    def _extend_word_list(self):
        word_page = self._get_new_word_page()
        self._words.extend(word_page)
        self._new_word_iterator = iter(word_page)

    def _get_new_word_page(self, n: int = 100) -> list[str]:
        word_page = helpers.get_words(n)
        return word_page

    @property
    def words(self) -> list[str]:
        return self._words

    def get_new_word(self) -> str:
        word = next(self._new_word_iterator, None)
        if word is None:
            self._extend_word_list()
            word = next(self._new_word_iterator)
        return word


@dataclass
class LocalPlayer:
    local_id: int
    name: str
    score: int
    speed: float
    correct_words: int = 0
    incorrect_words: int = 0
    time_left: float = None
    is_ready: bool = False
    voted_for: str = None

    def add_word_iterator(self, words: list[str]):
        self._next_word = iter(words)

    def get_next_word(self) -> str:
        if not hasattr(self, '_next_word'):
            return
        return next(self._next_word)


class BasePlayerController(ABC):
    def __init__(self, session: GameSession):
        self._players_dict = {}
        self._local_id_counter = 0
        self._players_repr = self._init_repr()
        self._last_tick = None
        self.session = session

    def add_player(self, player: LocalPlayer):
        player.local_id = self._get_local_id()
        player.total_word_length = 0
        self._players_dict[player.local_id] = player
        self._insert_into_repr(player)

    def get_player(self, local_id: int):
        return self._players_dict.get(local_id, None)

    def remove_player(self, local_id: int):
        if local_id in self._players_dict:
            player = self._players_dict.pop(local_id)
            self._remove_from_repr(player)

    def handle_word(self, player: dict, word: str):
        player_obj = self.get_player(player['local_id'])
        self._handle_word(player_obj, word)
        self._update_repr_from_object(player_obj)

    @property
    def players_data(self):
        return self._players_repr

    @property
    def time_elapsed(self):
        return self.session.started_at - timezone.now()

    def _get_local_id(self):
        local_id = self._local_id_counter
        self._local_id_counter += 1
        return local_id

    @abstractmethod
    def _init_repr(self):
        pass

    @abstractmethod
    def _insert_into_repr(self, player):
        pass

    @abstractmethod
    def _remove_from_repr(self, player):
        pass

    @abstractmethod
    def _handle_word(self, player: LocalPlayer, word: str):
        pass

    @abstractmethod
    def _update_repr_from_object(self, player):
        pass

    @abstractmethod
    def make_tick(self):
        pass


class PlayerPlainController(BasePlayerController):
    def _init_repr(self):
        return dict()

    def _insert_into_repr(self, player):
        self._players_repr[player.local_id] = player.as_dict()

    def _remove_from_repr(self, player):
        self._players_repr.pop(player.local_id)

    def _update_repr_from_object(self, player):
        self._players_repr[player.local_id].update(player.as_dict())

    def _handle_word(self, player: LocalPlayer, word: str):
        if player.get_next_word() == word:
            player.score += len(word)
            player.correct_words += 1
        else:
            player.incorrect_words += 1
        player.total_word_length += len(word)
        player.speed = player.total_word_length / self.time_elapsed
        return player

    def make_tick(self):
        prev_tick = self._last_tick or self.session.started_at
        self._last_tick = timezone.now()
        time_delta = self._last_tick - prev_tick

        for player in self._players_dict.values():
            player.time_left -= time_delta
            self._update_repr_from_object(player)


class BaseGame(ABC):
    STATE_PREPARING = 'preparing'
    STATE_PLAYING = 'playing'
    STATE_VOTING = 'voting'

    word_provider_class = WordListProvider
    player_controller_class = PlayerPlainController
    player_class = LocalPlayer

    def __init__(self, session_id=None):
        self._session = GameSession.objects.get(session_id=session_id)
        if self._session.is_finished:
            raise GameOverError

        self._state = self.STATE_PREPARING
        self._player_controller = self.player_controller_class(self._session)
        self._event_handlers = self._init_event_handlers()
        self._word_provider = self.word_provider_class()

    def player_event(self, event: Event) -> list[Event]:
        if not event.is_valid():
            raise InvalidMessageError
        handler = self._get_event_handler(event.type)
        events = handler(**event.data)
        return events

    @property
    def _players(self):
        return self._player_controller.players_data

    def _init_event_handlers(self):
        event_handlers = {
            Event.PLAYER_JOINED: self._handle_player_join,
            Event.PLAYER_LEFT: self._handle_player_leave,
            Event.PLAYER_WORD: self._handle_word,
            Event.TRIGGER_TICK: self._handle_tick,
            Event.PLAYER_READY_STATE: self._handle_player_ready,
            Event.PLAYER_MODE_VOTE: self._handle_player_vote,
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

    ### Event handlers start here ##

    def _handle_player_join(self, player) -> list[Event]:
        if self._can_player_join():
            self._add_player(player)
            events = []

            players_message = {'players': self._players}
            events.append(
                Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_PLAYERS_UPDATE, data=players_message),
            )

            words_message = {'words': self._word_provider.words}
            events.append(
                Event(target=Event.TARGET_PLAYER,
                      type=Event.SERVER_WORDS, data=words_message),
            )

            return events
        raise PlayerJoinRefusedError

    def _handle_player_leave(self, player) -> list[Event]:
        self._remove_player(player)

        message = {'players': self._players}
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_PLAYERS_UPDATE, data=message)
        return [event]

    def _handle_word(self, player, word) -> list[Event]:
        self._player_controller.handle_word(player, word)
        message = {'word': self._word_provider.get_new_word(),
                   'players': self._players}
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_NEW_WORD, data=message)
        return [event]

    def _handle_tick(self) -> list[Event]:
        events = []
        if self._state is self.STATE_PLAYING:
            self._player_controller.make_tick()
            tick_event = Event(type=Event.SERVER_TICK,
                               target=Event.TARGET_ALL, data=self._players)
            events.append(tick_event)
        elif self._state is self.STATE_VOTING:
            # TODO: voting protocol
            if self._vote_timeout():
                event = Event(target=Event.TARGET_ALL,
                              type=Event.SERVER_START_GAME,
                              data=self._vote_results)
                events.append(event)
        return events

    def _handle_player_ready(self, data) -> list[Event]:
        events = []
        if self._state is self.STATE_PREPARING:
            self._update_players(data)
            event = Event(target=Event.TARGET_ALL,
                          type=Event.SERVER_PLAYERS_UPDATE, data=self._players)
            events.append(event)
            if self._can_start():
                start_game_event = self._start_game()
                events.append(start_game_event)
        return events

    def _handle_player_vote(self, data):
        events = []
        if self._state is self.STATE_VOTING:
            self._update_players(data)
            event = Event(target=Event.TARGET_ALL,
                          type=Event.SERVER_VOTES_UPDATE, data=self._players)
            events.append(event)
            if self._voting_finished():
                event = Event(target=Event.TARGET_ALL,
                              type=Event.SERVER_START_GAME,
                              data=self._vote_results)
                events.append(event)
        return events

    def _init_player(self, player: dict):
        player_obj = self.player_class(**player)
        player_obj.add_word_iterator(self._word_provider.words)
        return player_obj

    def _add_player(self, player: dict):
        player_obj = self._init_player(player)
        self._player_controller.add_player(player_obj)

    def _remove_player(self, player: dict):
        self._player_controller.remove_player(player['local_id'])

    def _get_player(self, player: dict):
        return self._player_controller.get_player(player['local_id'])

    def _can_player_join(self):
        if 0 < self._session.max_players <= self._players_count:
            return False
        if self._state is not self.STATE_PREPARING:
            return False
        return True

    def _start_game(self) -> Event:
        """
        Updates controller and database record state to STATE_PLAYING.

        NOTE: this function is used heavily in unit tests to alter game state.
        """
        self._state = self.STATE_PLAYING
        self._session.start_game()

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_START_GAME, data={})
        return event

    def _game_over(self) -> Event:
        """
        Updates controller and database record state to STATE_VOTING.

        NOTE: this function is used heavily in unit tests to alter game state.
        """
        self._state = self.STATE_VOTING
        self._session.save_results()
        # TODO: rename .save_results() to .end_game() for readability

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_GAME_OVER, data=self._results())
        return event

    def _voting_finished(self):
        return self._vote_count == self._players_count

    @property
    def _players_count(self):
        return len(self._players_list)

    @property
    def _vote_count(self):
        return len([vote for vote in self._vote_list
                    if vote['mode'] is not None])

    @abstractmethod
    @property
    def _vote_list(self):
        pass

    @abstractmethod
    @property
    def _players_list(self):
        pass

    @abstractmethod
    def _insert_player_into_repr(self, player):
        pass

    @abstractmethod
    def _remove_player_from_repr(self, player):
        pass

    @abstractmethod
    def _is_valid_message(self):
        pass

    @abstractmethod
    def _check_vote_timeout(self):
        pass

    @abstractmethod
    def _update_players(self, players):
        pass

    @abstractmethod
    def _can_start(self):
        pass

    @abstractmethod
    def _switch_team(self):
        pass


class SingleGameController(BaseGame):
    # TODO: add proper definitions
    pass
