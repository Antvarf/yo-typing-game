import os
import json

from E.settings import BASE_DIR


def get_regular_words():
    with open(os.path.join(BASE_DIR, "ozhegow_regular_words.json"), "r") as e:
        words = json.loads(e.read())
    return words

def get_yo_words():
    with open(os.path.join(BASE_DIR, "yo_words.json"), "r") as e:
        words = json.loads(e.read())
    return words
