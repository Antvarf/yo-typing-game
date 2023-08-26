class ControllerError(Exception):
    pass


class DiscardedEvent(ControllerError):
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
