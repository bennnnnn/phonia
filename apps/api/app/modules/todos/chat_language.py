# ruff: noqa: RUF001 - the Turkish dotless i and the typographic apostrophe are matched words
"""Which chat messages may add or change to-dos: those written in English.

The server reads a chat to-do change against the user's own words (the time they
said, "mark it done", "remind me…"), and that reading is English. A message in
another language reads its to-dos in chat; adding or changing one happens in the
To-do screen, which the reply offers as a button (a ```todo_link fence).

A message counts as another language on positive evidence: letters of another
script (Cyrillic, Ethiopic, …), or at least two words that only the app's other
Latin-script languages use. Any English to-do word keeps it English, so "remind me
to call Getachew ነገ at 10am" still saves. A message with no language of its own
("a las 5", "17:00", "sí") follows the chat: the user's previous message, then their
app language. An answer to "¿cuándo?" never writes either.
"""

from __future__ import annotations

import re
import unicodedata

from app.core.validation import normalize_locale_code

TODO_LINK_FENCE = "todo_link"

_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
# Words that put a to-do request in English, whatever else the message holds.
_ENGLISH_TODO = frozenset(
    {
        "remind",
        "reminder",
        "reminders",
        "to-do",
        "to-dos",
        "task",
        "tasks",
        "tomorrow",
        "today",
        "tonight",
        "add",
        "delete",
        "remove",
        "mark",
        "done",
        "schedule",
        "reschedule",
        "cancel",
        "uncheck",
        "complete",
        "move",
        "list",
        "every",
    }
)
# Words of Spanish, French, German, Italian, Portuguese and Turkish that English
# does not use: articles, pronouns, days, and the to-do and time words.
_OTHER_LATIN_BY_LANGUAGE: dict[str, frozenset[str]] = {
    "es": frozenset({
        "el", "los", "las", "del", "que", "qué", "mañana", "manana", "hoy", "recuérdame",
        "recuerdame", "recordatorio", "recordatorios", "añade", "anade", "agrega", "agregar",
        "borra", "borrar", "elimina", "eliminar", "quita", "mis", "lista", "tarea", "tareas",
        "llamar", "tengo", "pendientes", "lunes", "martes", "miércoles", "jueves", "viernes",
        "sábado",
    }),
    "fr": frozenset({
        "les", "des", "une", "demain", "aujourd'hui", "rappelle-moi", "rappelle", "rappel",
        "rappels", "ajoute", "ajouter", "supprime", "supprimer", "mes", "pour", "avec",
        "tâche", "tâches", "liste", "appeler", "lundi", "mardi", "mercredi", "jeudi",
        "vendredi", "samedi", "dimanche",
    }),
    "de": frozenset({
        "der", "das", "und", "eine", "morgen", "heute", "erinnere", "erinnerung",
        "erinnerungen", "füge", "hinzu", "lösche", "entferne", "mich", "meine", "für", "mit",
        "uhr", "aufgabe", "aufgaben", "anrufen", "montag", "dienstag", "mittwoch",
        "donnerstag", "freitag", "samstag", "sonntag",
    }),
    "it": frozenset({
        "il", "gli", "della", "che", "domani", "oggi", "ricordami", "promemoria", "aggiungi",
        "cancella", "mia", "mie", "mio", "miei", "alle", "attività", "chiamare", "lunedì",
        "martedì", "mercoledì", "giovedì", "venerdì", "domenica",
    }),
    "pt": frozenset({
        "uma", "amanhã", "amanha", "hoje", "lembra-me", "lembre-me", "lembrete", "lembretes",
        "adiciona", "adicione", "apaga", "apague", "minha", "minhas", "meu", "meus", "às",
        "tarefa", "tarefas", "ligar", "terça", "quarta", "quinta", "sexta",
    }),
    "tr": frozenset({
        "yarın", "bugün", "hatırlat", "hatirlat", "hatırlatıcı", "hatırlatma", "ekle", "sil",
        "benim", "için", "saat", "görev", "görevler", "görevlerim", "listeme", "listeye",
        "beni", "bana", "pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi",
    }),
}  # fmt: skip
_OTHER_LATIN: frozenset[str] = frozenset().union(*_OTHER_LATIN_BY_LANGUAGE.values())
_OTHER_LATIN_WORDS = 2


def _other_script(text: str) -> bool:
    return any(char.isalpha() and not _is_latin(char) for char in text)


def _is_latin(char: str) -> bool:
    try:
        return unicodedata.name(char).startswith("LATIN")
    except ValueError:
        return False


def writes_todos_in_todo_screen(
    text: str | None, *, prior_user: str | None = None, locale: str | None = None
) -> bool:
    """True when the to-do changes ``text`` asks for are made in To-do, never in chat.

    ``prior_user`` is the user's previous message and ``locale`` their app language:
    a message with no language of its own takes the first of them that has one.
    """
    if not text or not text.strip():
        return False
    for said in (text, prior_user):
        other = _is_other_language(said)
        if other is not None:
            return other
    return normalize_locale_code(locale) != "en"


def _is_other_language(text: str | None) -> bool | None:
    """True for another language, False for English, None when ``text`` can't tell."""
    if not text or not text.strip():
        return None
    words = [word.casefold() for word in _WORD.findall(text)]
    if any(word in _ENGLISH_TODO for word in words):
        return False
    if _other_script(text):
        return True
    if len({word for word in words if word in _OTHER_LATIN}) >= _OTHER_LATIN_WORDS:
        return True
    return None


# The app's languages written in another script, by the Unicode name of their letters.
_SCRIPT_LANGUAGE = (("CYRILLIC", "ru"), ("ETHIOPIC", "am"))
# The line above the To-do button when a reply wrote none of its own. The screen is
# named as the app names it in that language (mobile i18n ``todos.open_from_chat``).
_TODO_SCREEN_LINE = {
    "en": "You can add or change it in **To-do**.",
    "es": "Puedes añadirlo o cambiarlo en **Tareas**.",
    "fr": "Vous pouvez l'ajouter ou le modifier dans **Tâches**.",
    "de": "Du kannst das unter **Aufgaben** hinzufügen oder ändern.",
    "it": "Puoi aggiungerlo o modificarlo in **Attività**.",
    "pt": "Você pode adicionar ou alterar isso em **Tarefas**.",
    "tr": "**Yapılacaklar** bölümünden ekleyebilir veya değiştirebilirsiniz.",
    "ru": "Добавить или изменить это можно в разделе **Задачи**.",
    "am": "በ**የሚደረጉ** ውስጥ ማከል ወይም መቀየር ይችላሉ።",
}


def message_language(text: str | None) -> str | None:
    """Which of the app's other languages ``text`` is written in; None when it can't tell."""
    if not text:
        return None
    for char in text:
        if char.isalpha() and not _is_latin(char):
            name = unicodedata.name(char, "")
            return next((code for script, code in _SCRIPT_LANGUAGE if script in name), None)
    words = {word.casefold() for word in _WORD.findall(text)}
    counts = {code: len(words & vocab) for code, vocab in _OTHER_LATIN_BY_LANGUAGE.items()}
    code, count = max(counts.items(), key=lambda item: item[1])
    return code if count else None


def language_evidence(text: str | None) -> dict[str, int]:
    """How much of each app language ``text`` holds: letters of its script (Cyrillic,
    Ethiopic), or words only it uses. English is the reader's default, not counted here;
    the chat's reply language weighs these against English words."""
    counts: dict[str, int] = {}
    if not text:
        return counts
    for char in text:
        if char.isalpha() and not _is_latin(char):
            name = unicodedata.name(char, "")
            code = next((code for script, code in _SCRIPT_LANGUAGE if script in name), None)
            if code:
                counts[code] = counts.get(code, 0) + 1
    words = {word.casefold() for word in _WORD.findall(text)}
    for code, vocab in _OTHER_LATIN_BY_LANGUAGE.items():
        if found := len(words & vocab):
            counts[code] = found
    return counts


def todo_screen_line(language: str | None) -> str:
    """One line saying the change is made in To-do, in ``language`` (English otherwise)."""
    return _TODO_SCREEN_LINE.get(normalize_locale_code(language), _TODO_SCREEN_LINE["en"])


def todo_screen_answer(language: str | None) -> str:
    """The whole reply to a to-do change chat can't make: the line, then the button."""
    return f"{todo_screen_line(language)}\n\n```{TODO_LINK_FENCE}\n```"
