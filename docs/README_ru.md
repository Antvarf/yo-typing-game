# Yo-typing (версия 2.1.5) <img src="../favicon.png" height="25px">
For english version of the docs [click here](../README.md)

## Содержание

- [Обзор](#обзор)
- [Особенности](#особенности)
  * [Различные игровые режимы](#различные-игровые-режимы)
  * [Одиночный режим и мультиплеер](#одиночный-режим-и-мультиплеер)
  * [Сохранение статистики игр](#сохранение-статистики-игр)
  * [Больше!](#больше)
- [Создано с использованием](#создано-с-использованием)
- [Примечание от разработчика](#примечание-от-разработчика)

## Обзор

Этот репозиторий содержит исходный код **бэкенда** *yo-typing* - соревновательной
онлайн игры-тренажера про печать на скорость с акцентом на наличие слов,
содержащих букву "Ё", для печати.

<img src="screenshot.png" />

**Демо доступно по ссылке:** https://yo-typing.ru/

## Особенности

### Различные игровые режимы

В нашей игре доступны различные режимы! На текущий момент это:
* **Обычный** - каждый игрок получает общий набор слов и 60 секунд на то,
  чтобы ввести их корректно. Выигрывает получивший наибольшее количество очков!
* **Железный** - похож на обычный, но стирание в нём запрещено, поэтому будьте
  внимательны! Можно использовать для тренировки аккуратности печати.
* **Бесконечный** - дано только 30 секунд, однако их *можно* вернуть, вводя слова
  правильно! Время будет бежать быстрее с каждым моментом, так что пусть
  даже бесконечный набор слов в запасе не даст вам расслабиться. Выиграет
  переживший своих оппонентов! 
* **Перетягивание каната** - команда на команду! Вводите правильно как можно
  больше слов так быстро как сможете, и перетягивайте канат разницы очков между
  командами на свою сторону! Именно разница очков между командами определяет 
  конечного победителя.

### Одиночный режим и мультиплеер

Данное приложение может помочь вам увеличить скорость печати, совмещая это с
увлекательным игровым элементом и опционально позволяя соревноваться в
мультиплеере со своими друзьями!

### Сохранение статистики игр

Вы также можете отслеживать свою статистику (средняя и лучшая скорость печати
в матчах, др.) и занять своё почётное место на доске лидеров, если пройдёте
короткую регистрацию 🐈.

### Больше!

Наш проект активно развивается и готовится к выходу на третью итерацию! Следите
за новостями, чтобы узнать подробности.

## Создано с использованием

На бэкенде проект использует ряд технологий и библиотек, среди них:
- [Python 3.10](https://www.python.org/downloads/release/python-3100/)
- [Django (v4.1.6)](https://www.djangoproject.com)
- [Django Rest Framework (v3.14.0)](https://django-rest-framework.org/)
- [Django Channels (v4.0.0)](https://github.com/django/channels)
- [drf-spectacular (v0.26.4)](https://github.com/tfranzel/drf-spectacular)

## Примечание от разработчика

Код был доработан до текущего состояния с целью обучения и более
тщательного следования как общим, так и специфичным для django рекомендациям
по его написанию, а также лучшим практикам, широко принятым в сообществе
разработчиков.

<u>В первую очередь, при доработке проекта  внимание уделялось:</u>
- Применению test-driven подхода для написания всей новой кодовой базы,
  покрытию тестами старой.
- Извлечению бизнес-логики для API и переносу в код моделей, минимизации кода
  для CRUD операций и использовании drf-yasg для документации.
- Отделению, насколько возможно, логики игры от логики обмена игровыми
  сообщениями (по протоколу вебсокет)
- Оптимизации запросов к БД через Django ORM и использованию агрегаций
  заместо избыточной денормализации в целях повышения целостности данных и
  читаемости кода.
