# Yo-typing (version 2.1.5) <img src="favicon.png" height="25px">
Для версии страницы на русском [нажмите тут](docs/README_ru.md)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
  * [Various game modes](#various-game-modes)
  * [Play with your friends](#play-with-your-friends)
  * [Save your stats](#save-your-stats)
  * [Moreeee!](#moreeee)
- [Built With](#built-with)
- [A word from developer](#a-word-from-developer)

## Overview

This repo hosts **exclusively backend** code for yo-typing - a competitive
online game with an accent put on words using cyrillic letter "Ё" present.

<img src="docs/screenshot.png" />

**Live demo is available at:** https://yo-typing.ru/

## Features

### Various game modes

Modes available currently are:
* **Classic** - each player gets a common set of words and 60 seconds to
  type them accurately. Whoever gets the most points wins!
* **Ironwall** - same as classic, however backspace is disabled, so be
  careful! Can be used to improve typing accuracy.
* **Endless** - only 30 seconds are given, however you *can* take them back
  by entering the words properly, and the word amount is infinite! However,
  the clock is at advantage of ticking faster at every moment, so
  don't let it get too much ahead :^ Last player standing wins!
* **Tug Of War** - team vs team! Type as many words correctly as
  fast as you can and get ahead of the opposite team by pulling the tug
  on your side! Team points difference is what gets you a win.

### Play with your friends

This application can help by improving your typing speed while also
providing fun competition experience in the multiplayer with your friends!

### Save your stats

You can also keep track of your stats (average and best typing speed +
more) if you sign up, as well as take place of honor in the leaderboard
among the others if you do 🐈

### Moreeee!

Our project is advancing further and will soon be entering major version 3!
Follow the repository news if you are interested :3

## Built With

Our backend uses many great tools and libraries, including:
- [Python 3.10](https://www.python.org/downloads/release/python-3100/)
- [Django (v4.1.6)](https://www.djangoproject.com)
- [Django Rest Framework (v3.14.0)](https://django-rest-framework.org/)
- [Django Channels (v4.0.0)](https://github.com/django/channels)
- [drf-spectacular (v0.26.4)](https://github.com/tfranzel/drf-spectacular)

## A word from developer

The project was refactored to the current state with the aim of learning and following
more closely both general and django-specific coding guidelines
and best practices adopted by the community.

<u>Specific accent was put on:</u>
- Adopting the test-driven approach for every piece of code written.
- Extracting business logic from code and keeping it in models
  exclusively (as one widely-supported alternative).
- Keeping logic that is unrelated to websockets (e.g. actual game
  mechanics) as separate as possible from the websocket consumer
  code.
- Optimizing database queries and leveraging aggregations instead of
  unneeded denormalization to improve both data integrity and code
  maintainability.


