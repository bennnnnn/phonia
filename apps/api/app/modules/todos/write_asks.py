# ruff: noqa: RUF001 - Turkish dotless i and Cyrillic letters are matched words
"""Which messages in another language ask to add or change a to-do.

Chat in another language only reads to-dos (``chat_language``). Asked to add one,
a model still asked "¿cuándo?" and then wrote "He añadido…", so such a request is
answered by the server: one line and the Open To-do button, no model call.

A request is a reminder phrase ("recuérdame", "напомни"), or an add or delete
verb beside a to-do target ("añade … a mis tareas"). Words with an everyday
meaning stay out: Spanish "tarea" (also homework), "todo" (all), "pon" (play) and
"marca" (brand), French "note" (a grade), Russian "задача" (a maths problem),
Amharic "ዝርዝር" (also details), German "ich erinnere mich" (I remember). After the
button, a reply with a time or a yes ("a las 5", "sí") asks the same thing again;
a question is a new one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.modules.todos.chat_language import (
    TODO_LINK_FENCE,
    message_language,
    todo_screen_answer,
    writes_todos_in_todo_screen,
)

# A phrase ending in "*" matches the start of a word (Turkish and Amharic add endings).
_REMIND = (
    # Spanish
    "recuérdame", "recuerdame", "recordarme", "pon un recordatorio",
    # French
    "rappelle-moi", "rappelez-moi", "fais-moi penser",
    # Italian
    "ricordami", "ricordarmi",
    # Portuguese
    "lembra-me", "lembre-me", "lembrar-me", "me lembra de", "me lembre de",
    # Turkish
    "hatırlat", "hatirlat", "hatırlatır mısın", "hatirlatir misin",
    # Russian
    "напомни", "напомните",
    # Amharic
    "አስታውሰኝ", "አስታውሺኝ", "አስታውሱኝ",
)  # fmt: skip
_ADD_OR_CHANGE = (
    "añade", "anade", "añadir", "agrega", "agregar", "apunta", "anota", "borra", "borrar",
    "elimina", "eliminar", "quita",
    "ajoute", "ajouter", "ajoutez", "mets", "supprime", "supprimer", "enlève", "enleve",
    "retire",
    "füge", "fuge", "trag", "trage", "lösche", "losche", "löschen", "entferne", "setz",
    "aggiungi", "aggiungere", "metti", "cancella", "elimina", "togli", "rimuovi",
    "adiciona", "adicione", "adicionar", "coloca", "coloque", "põe", "anote", "apaga",
    "apague", "remove", "remova", "exclui", "exclua",
    "ekle", "sil", "kaldır", "kaldir",
    "добавь", "добавьте", "запиши", "запишите", "удали", "удалите", "убери",
    "ጨምር", "ጨምሪ", "ጨምሩ", "ሰርዝ", "ሰርዢ", "አስገባ",
)  # fmt: skip
_TODO_TARGET = (
    "mis tareas", "a tareas", "en tareas", "mi lista", "lista de tareas", "mis pendientes",
    "lista de pendientes", "recordatorio", "recordatorios",
    "ma liste", "mes tâches", "mes taches", "liste de tâches", "rappel", "rappels",
    "meine liste", "meiner liste", "meine aufgaben", "meinen aufgaben", "aufgabenliste", "erinnerung", "erinnerungen",
    "la mia lista", "mia lista", "le mie attività", "le mie attivita", "promemoria",
    "minha lista", "minhas tarefas", "lista de tarefas", "lembrete", "lembretes",
    "listeme", "listeye", "listemden", "görevlerime", "yapılacaklar*", "yapilacaklar*",
    "мой список", "в список", "список дел", "мои задачи", "в задачи", "напоминание",
    "напоминания",
    "ዝርዝሬ*", "ተግባሮቼ*", "የሚደረጉ*",
    "to-do",
)  # fmt: skip
# German "erinnere mich" (remind me), never "ich erinnere mich" (I remember).
_GERMAN_REMIND_RE = re.compile(r"(?<!ich )(?<![\w'-])erinnere? mich(?![\w'-])")
# A time or a yes, answering the To-do button's turn again; a question is a new one.
_DIGIT = re.compile(r"\d")
_YES_OR_DAY = (
    "sí", "si", "oui", "ja", "sì", "sim", "evet", "да", "አዎ",
    "mañana", "manana", "demain", "morgen", "domani", "amanhã", "amanha", "yarın", "yarin",
    "завтра", "ነገ", "hoy", "aujourd'hui", "heute", "oggi", "hoje", "bugün", "сегодня", "ዛሬ",
)  # fmt: skip


def _pattern(phrases: Iterable[str]) -> re.Pattern[str]:
    parts = [
        re.escape(phrase[:-1]) if phrase.endswith("*") else re.escape(phrase) + r"(?![\w'-])"
        for phrase in phrases
    ]
    return re.compile(r"(?<![\w'-])(?:" + "|".join(parts) + ")")


_REMIND_RE = _pattern(_REMIND)
_ADD_OR_CHANGE_RE = _pattern(_ADD_OR_CHANGE)
_TODO_TARGET_RE = _pattern(_TODO_TARGET)
_YES_OR_DAY_RE = _pattern(_YES_OR_DAY)


def asks_to_change_todos(text: str | None, *, prior_assistant: str | None = None) -> bool:
    """True when ``text``, in another language, asks to add, change or delete a to-do.

    ``prior_assistant`` is the reply before it: after the To-do button, a time or a
    yes is the same request again.
    """
    folded = " ".join((text or "").casefold().split())
    if not folded:
        return False
    if _REMIND_RE.search(folded) or _GERMAN_REMIND_RE.search(folded):
        return True
    if _ADD_OR_CHANGE_RE.search(folded) and _TODO_TARGET_RE.search(folded):
        return True
    after_button = f"```{TODO_LINK_FENCE}" in (prior_assistant or "")
    if not after_button or "?" in folded:
        return False
    return bool(_DIGIT.search(folded) or _YES_OR_DAY_RE.search(folded))


def todo_screen_reply(
    text: str | None,
    *,
    prior_user: str | None = None,
    prior_assistant: str | None = None,
    locale: str | None = None,
) -> str | None:
    """The server's whole reply to a to-do change asked in another language, else None."""
    if not writes_todos_in_todo_screen(text, prior_user=prior_user, locale=locale):
        return None
    if not asks_to_change_todos(text, prior_assistant=prior_assistant):
        return None
    return todo_screen_answer(message_language(text) or message_language(prior_user) or locale)
