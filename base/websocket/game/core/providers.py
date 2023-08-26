from __future__ import annotations

from base.websocket.game import helpers


class WordListProvider:
    def __init__(self):
        self._words = []
        self._new_word_iterator = iter([])
        self._extend_word_list(init=True)

    def _extend_word_list(self, init=False):
        word_page = self._get_new_word_page()
        self._words.extend(word_page)
        if not init:
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
