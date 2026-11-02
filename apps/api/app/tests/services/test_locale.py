import pytest

from app.services.locale import REPLY_LANGUAGE_ORDER, locale_display_name, locale_system_hint


@pytest.mark.parametrize(
    "locale, expected",
    [
        ("am", "Amharic"),
        ("es", "Spanish"),
        ("en-US", "English"),
        (None, "English"),
    ],
)
def test_locale_display_name(locale, expected):
    assert locale_display_name(locale) == expected


def test_an_english_app_names_its_reply_language_and_what_outranks_it():
    """An English app had no language line; a saved "replies in Spanish" decided instead."""
    for locale in ("en", None, "en-US"):
        hint = locale_system_hint(locale)
        assert hint.startswith("The user's app language is English (locale code: en)")
        assert hint.endswith(REPLY_LANGUAGE_ORDER)


def test_locale_system_hint_amharic():
    hint = locale_system_hint("am")
    assert hint is not None
    assert "Amharic" in hint
    assert "am" in hint
    assert hint.endswith(REPLY_LANGUAGE_ORDER)
