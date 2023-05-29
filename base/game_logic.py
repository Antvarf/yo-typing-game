import random
import secrets
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, asdict
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
    SERVER_ERROR = 'error'
    # SERVER_USERNAME_SWITCH = 'username_switch'

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
    id: int
    displayed_name: str
    score: int = 0
    speed: float = 0
    correct_words: int = 0
    incorrect_words: int = 0
    total_word_length: int = 0
    mistake_ratio: float = 0.0
    time_left: float = None
    is_ready: bool = False
    is_winner: bool = False
    voted_for: str = None

    def __init__(self, player: Player):
        super().__init__()
        self._next_word = None
        self.db_record = player
        self.displayed_name = player.displayed_name
        self.old_displayed_name = None
        self.id = player.pk

    def add_word_iterator(self, words: list[str]):
        self._next_word = iter(words)

    def get_next_word(self) -> str:
        if self._next_word is None:
            return
        return next(self._next_word)

    def to_dict(self) -> dict:
        result = asdict(self)
        return result


class BasePlayerController(ABC):
    """
    A class responsible for:
        * tracking last local player id added
        * updating player scores when word is submitted
        * maintaining players representation for display
        * updating player related fields on session record
    """
    def __init__(self, session: GameSession):
        self._displayed_names = set()
        self._players_dict = {}
        self._players_repr = self._init_repr()
        self._ready_count = 0
        self._voted_count = 0
        self._last_tick = None
        self.session = session

    def add_player(self, player: LocalPlayer):
        self.add_to_unique_displayed_names(player)
        self._players_dict[player.id] = player
        self._insert_into_repr(player)
        self._perform_database_update(self.session, player)

    def get_player(self, id: int) -> LocalPlayer | None:
        return self._players_dict.get(id, None)

    def remove_player(self, id: int):
        if id in self._players_dict:
            player = self._players_dict.pop(id)
            if player.is_ready:
                self._ready_count -= 1
            if player.voted_for is not None:
                self._voted_count -= 1
            self._remove_from_repr(player)
            self.remove_from_unique_displayed_names(player)
            self._perform_database_update(self.session, player)

    def handle_word(self, player_id: int, word: str):
        player_obj = self.get_player(player_id)
        self._handle_word(player_obj, word)
        self._update_repr_from_object(player_obj)

    @property
    def players_data(self):
        return self._players_repr

    @property
    def player_count(self):
        return len(self._players_dict)

    @property
    def ready_count(self):
        return self._ready_count

    @property
    def voted_count(self):
        return self._voted_count

    @property
    def votes(self) -> Counter:
        counts = Counter(v.voted_for
                         for v in self._players_dict.values() if v.voted_for)
        return counts
    
    def add_to_unique_displayed_names(self, player: LocalPlayer):
        new_displayed_name = \
            player.old_displayed_name = player.displayed_name
        while new_displayed_name in self._displayed_names:
            tag = secrets.token_urlsafe(3)
            new_displayed_name = f'{player.displayed_name}#{tag}'
        player.displayed_name = new_displayed_name
        self._displayed_names.add(player.displayed_name)
        return

    def remove_from_unique_displayed_names(self, player: LocalPlayer):
        self._displayed_names.remove(player.displayed_name)
        player.displayed_name = player.old_displayed_name
        return

    def set_ready_state(self, id: int, state: bool):
        """
        Updates player's ready state and the ready_count counter accordingly
        """
        player = self.get_player(id)
        if player is not None and player.is_ready != state:
            player.is_ready = state
            self._ready_count += 1 if state else -1
        return

    def set_player_vote(self, id: int, mode: str):
        """
        Updates players vote and the voted_count counter accordingly
        """
        player = self.get_player(id)
        if player is not None and mode in GameModes.labels:
            if player.voted_for is None:
                self._voted_count += 1
            player.voted_for = mode
        return

    def set_time_left(self, id: int, time_left: float):
        """
        Sets the players .time_left field to :time_left:
        """
        player = self.get_player(id)
        if player is not None:
            player.time_left = time_left
            self._update_repr_from_object(player)
        return

    @property
    def time_elapsed(self) -> int:
        if self.session.started_at is None:
            return 0
        delta = self.session.started_at - timezone.now()
        return delta.total_seconds() + 1

    def _perform_database_update(self, session: GameSession, player: LocalPlayer):
        self._update_session_record(session)
        self._update_player_record(player)

    def _update_session_record(self, session: GameSession):
        session.players_now = self.player_count
        session.save()

    def _update_player_record(self, player: LocalPlayer):
        player.db_record.displayed_name = player.displayed_name
        player.db_record.save()

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
        self._players_repr[player.id] = asdict(player)

    def _remove_from_repr(self, player):
        self._players_repr.pop(player.id)

    def _update_repr_from_object(self, player):
        self._players_repr[player.id].update(asdict(player))

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
            player.time_left -= time_delta.total_seconds()
            self._update_repr_from_object(player)


class BaseGame(ABC):
    STATE_PREPARING = 'preparing'
    STATE_PLAYING = 'playing'
    STATE_VOTING = 'voting'

    word_provider_class = WordListProvider
    player_controller_class = PlayerPlainController
    player_class = LocalPlayer

    START_GAME_DELAY = 0

    def __init__(self, session_id=None):
        self._session = GameSession.objects.get(session_id=session_id)
        if self._session.is_finished:
            raise GameOverError

        self._state = self.STATE_PREPARING
        self._player_controller = self.player_controller_class(self._session)
        self._event_handlers = self._init_event_handlers()
        self._word_provider = self.word_provider_class()
        self._modes_available = GameModes.labels
        self._game_begins_at = None

    def player_event(self, event: Event) -> list[Event]:
        if not event.is_valid():
            raise InvalidMessageError
        handler = self._get_event_handler(event.type)
        events = handler(**event.data.to_dict())
        return events

    @property
    def _players(self):
        return self._player_controller.players_data

    def _init_event_handlers(self):
        event_handlers = {
            Event.PLAYER_JOINED: self._handle_player_join,
            Event.PLAYER_LEFT: self._handle_player_leave,
            Event.PLAYER_READY_STATE: self._handle_player_ready,
            Event.PLAYER_WORD: self._handle_word,
            Event.TRIGGER_TICK: self._handle_tick,
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

    ### Event handlers start here ###

    def _handle_player_join(self, player: Player) -> list[Event]:
        """
        Event handler for player joining the session.
        """
        events = []
        if self._can_player_join(player):
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
            events.append(self._get_players_update_event())
            if not self._player_count and self._state is self.STATE_PLAYING:
                events.append(self._game_over())
            if self._can_start():
                game_begins_event = self._get_game_begins_event()
                events.append(game_begins_event)
                if self.START_GAME_DELAY <= 0:
                    start_game_event = self._start_game()
                    events.append(start_game_event)
                else:
                    self._stage_start_game(self.START_GAME_DELAY)
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
                if self.START_GAME_DELAY <= 0:
                    start_game_event = self._start_game()
                    events.append(start_game_event)
                else:
                    self._stage_start_game(self.START_GAME_DELAY)
        return events

    def _handle_word(self, player: Player, payload: str) -> list[Event]:
        events = []
        if self._state is self.STATE_PLAYING:
            self._player_controller.handle_word(player.pk, payload)
            events.append(self._get_new_word_event())
            events.append(self._get_players_update_event())
        return events

    def _handle_tick(self, **kwargs) -> list[Event]:
        events = []
        if self._state is self.STATE_PREPARING:
            if self._game_begins_at is not None:
                if timezone.now() >= self._game_begins_at:
                    events.append(self._start_game())

        elif self._state is self.STATE_PLAYING:
            if self._is_game_over():
                events.append(self._game_over())
            else:
                self._player_controller.make_tick()
                events.append(self._get_players_update_event())

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

    def _get_initial_state_event(self, player: LocalPlayer) -> Event:
        event = Event(
            target=Event.TARGET_PLAYER,
            type=Event.SERVER_INITIAL_STATE,
            data={
                'player': player.to_dict(),
                'players': self._players,
                'words': self._word_provider.words,
            }
        )
        return event

    def _get_players_update_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_PLAYERS_UPDATE,
                      data={'players': self._players})
        return event

    def _get_game_begins_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_GAME_BEGINS,
                      data=self.START_GAME_DELAY)
        return event

    def _get_new_word_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_NEW_WORD,
                      data=self._word_provider.get_new_word())
        return event

    def _get_votes_update_event(self) -> Event:
        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_VOTES_UPDATE,
                      data=self._player_controller.votes)
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

    def _init_player(self, player: Player):
        player_obj = self.player_class(player)
        player_obj.add_word_iterator(self._word_provider.words)
        return player_obj

    def _add_player(self, player: Player) -> LocalPlayer:
        player_obj = self._init_player(player)
        self._player_controller.add_player(player_obj)
        # TODO: don't rely on object modification
        return player_obj

    def _remove_player(self, player: Player):
        self._player_controller.remove_player(player.pk)

    def _get_player(self, player: Player) -> LocalPlayer | None:
        return self._player_controller.get_player(player.pk)

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

    def _can_player_join(self, player: Player) -> bool:
        if 0 < self._session.players_max <= self._player_count:
            return False
        if self._state is not self.STATE_PREPARING:
            return False
        if self._player_exists(player):
            return False
        return True

    def _player_exists(self, player: Player) -> bool:
        """
        Checks if player with given player record is present in the session
        """
        return bool(self._get_player(player) is not None)

    def _set_ready_state(self, player: Player, state: bool):
        self._player_controller.set_ready_state(player.pk, state)

    def _set_player_vote(self, player: Player, mode: str):
        self._player_controller.set_player_vote(player.pk, mode)

    @property
    def _player_count(self) -> int:
        return self._player_controller.player_count

    def _stage_start_game(self, countdown: int):
        """
        Set _game_begins_at for future ticks to compare tz.now() against
        """
        offset = timezone.timedelta(seconds=countdown)
        self._game_begins_at = timezone.now() + offset

    def _start_game(self) -> Event:
        """
        Updates controller and database record state to STATE_PLAYING.

        NOTE: this function is used heavily in unit tests to alter game state.
        TODO: test me (please!)
        """
        self._state = self.STATE_PLAYING
        self._session.start_game()

        self._post_start()

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_START_GAME, data={})
        return event

    def _game_over(self) -> Event:
        """
        Updates controller and database record state to STATE_VOTING.

        NOTE: this function is used heavily in unit tests to alter game state.
        TODO: test me (please!)
        """
        self._state = self.STATE_VOTING
        self._session.game_over()
        self._session.save_results(self.results)
        # TODO: rename .save_results() to .end_game() for readability

        event = Event(target=Event.TARGET_ALL,
                      type=Event.SERVER_GAME_OVER, data=self.results)
        return event

    @abstractmethod
    def _post_start(self):
        # TODO: reimplement it using decorators?
        pass

    @abstractmethod
    def _is_game_over(self) -> bool:
        pass

    @property
    @abstractmethod
    def results(self):
        pass

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
        self._new_session_id = new_session
        self._state = None
        event = self._get_new_game_event()
        return event


class SingleGameController(BaseGame):
    GAME_DURATION_SEC = 60

    @property
    def results(self) -> list[dict]:
        return self._players.values()

    def _post_start(self):
        offset = timezone.timedelta(seconds=self.GAME_DURATION_SEC)
        for p in self._players:
            self._player_controller.set_time_left(p, self.GAME_DURATION_SEC)
        self._game_ends_at = self._session.started_at + offset

    def _is_game_over(self) -> bool:
        if self._state is not self.STATE_PLAYING:
            return False
        return self._game_ends_at <= timezone.now()
