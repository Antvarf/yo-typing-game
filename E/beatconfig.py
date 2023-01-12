from datetime import timedelta


BEAT_SCHEDULE = {
    "game-tick": [
        {
            "type": "game.tick",
            "message": {"what": "idk"},
            "schedule": timedelta(milliseconds=250),
        },
    ],
}
