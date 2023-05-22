import os
import json
import random

from E.settings import BASE_DIR


def get_regular_words():
    with open(os.path.join(BASE_DIR, "ozhegow_regular_words.json"), "r") as e:
        words = json.loads(e.read())
    return words


def get_yo_words():
    with open(os.path.join(BASE_DIR, "yo_words.json"), "r") as e:
        words = json.loads(e.read())
    return words


def get_words(n: int):
    yo_words_cnt = int(n * 0.1)
    words_cnt = n - yo_words_cnt

    words = random.choices(get_regular_words(), k=words_cnt) \
            + random.choices(get_yo_words(), k=yo_words_cnt)
    random.shuffle(words)
    return words
