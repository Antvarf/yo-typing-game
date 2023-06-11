import os
import json
import random

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def get_regular_words():
    with open(os.path.join(settings.BASE_DIR, "ozhegow_regular_words.json"), "r") as e:
        words = json.loads(e.read())
    return words


def get_yo_words():
    with open(os.path.join(settings.BASE_DIR, "yo_words.json"), "r") as e:
        words = json.loads(e.read())
    return words


def get_words(n: int):
    yo_words_cnt = int(n * 0.1)
    words_cnt = n - yo_words_cnt

    words = random.choices(get_regular_words(), k=words_cnt) \
            + random.choices(get_yo_words(), k=yo_words_cnt)
    random.shuffle(words)
    return words


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
