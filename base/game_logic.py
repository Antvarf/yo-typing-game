from abc import ABC, abstractmethod
from dataclasses import dataclass

from base.models import GameSession


@dataclass
class Event:
    PLAYER_JOINED = 'player_joined'
    PLAYER_LEFT = 'player_left'
    PLAYER_WORD = 'word'
    PLAYER_READY = 'player_ready'
    TRIGGER_TICK = 'tick'

    SERVER_NEW_WORD = 'new_word'
    SERVER_TICK = TRIGGER_TICK
    SERVER_START_GAME = 'start_game'

    TARGET_ALL = 'all'

    target: str
    type: str
    data: dict


class PlayerJoinRefusedError(Exception):
    pass


class EventTypeNotDefinedError(Exception):
    pass


class BaseGame(ABC):
    def __init__(self, session_id=None):
        self._session = GameSession.objects.get(session_id=session_id)
        assert self._session.mode == self.mode
        self._players = self._init_players()
        self._has_started = False

    def player_event(self, event: Event) -> list[Event]:
        event_handlers = {
            Event.PLAYER_JOINED: self._add_player,
            Event.PLAYER_LEFT: self._remove_player,
            Event.PLAYER_WORD: self._handle_word,
            Event.TRIGGER_TICK: self._tick,
            Event.PLAYER_READY: self._player_ready,
        }
        try:
            handler = event_handlers[event.type]
            events = handler(event.data)
        except KeyError:
            raise EventTypeNotDefinedError
        return events

    def _add_player(self, player) -> list[Event]:
        if self._can_player_join():
            events = self._insert_player(player)
            return events
        raise PlayerJoinRefusedError

    def _tick(self) -> list[Event]:
        if self._has_started:
            events = self._make_tick()
            return events

    def _player_ready(self, data) -> list[Event]:
        assert set(['player', 'ready']) == data.keys()
        if not self._has_started:
            self._update_players(data)
            if self._can_start():
                event = Event(target=Event.TARGET_ALL,
                              type=Event.SERVER_START_GAME, data={})
                return [event]

    @abstractmethod
    def _make_tick(self):
        pass

    @abstractmethod
    def _init_players(self):
        pass

    @abstractmethod
    def _can_player_join(self):
        pass

    @abstractmethod
    def _insert_player(self):
        pass

    @abstractmethod
    def _remove_player(self):
        pass

    @abstractmethod
    def _handle_word(self):
        pass
