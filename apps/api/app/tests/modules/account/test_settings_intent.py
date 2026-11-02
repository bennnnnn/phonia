"""The theme is the one setting a chat line changes; every other setting is changed in Settings."""

import pytest

from app.modules.account.settings_intent import SettingsChange, extract_settings_changes


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("switch to dark mode", "dark"),
        ("use light theme", "light"),
        ("change appearance to system", "system"),
        ("switch to default theme", "system"),
        ("set appearance to default", "system"),
        ("dark mode", "dark"),
        ("can you switch to dark mode?", "dark"),
        ("make the app theme follow my phone's setting", "system"),
        ("switch to dark mode pls, writing in bed and the screen is blinding", "dark"),
    ],
)
def test_a_theme_line_proposes_the_theme(text: str, value: str) -> None:
    assert extract_settings_changes(text) == [SettingsChange("appearance", value)]


@pytest.mark.parametrize(
    "text",
    [
        # A sum once proposed a model ("plus" read as a plan's model).
        "2 plus 2",
        "what is 2 plus 2",
        # Model, tone, language and memory are changed by hand in Settings.
        "use pro",
        "switch to flash",
        "switch the model to GPT",
        "use auto",
        "be more professional",
        "be funnier",
        "softer tone",
        "make your replies funnier",
        "switch language to Spanish",
        "reply in Amharic from now on",
        "always reply in French",
        "from now on talk to me in a more casual tone",
        "turn memory off",
    ],
)
def test_no_other_setting_is_proposed_from_chat(text: str) -> None:
    assert extract_settings_changes(text) == []


def test_two_changes_in_one_line_propose_only_the_theme() -> None:
    assert extract_settings_changes("switch to dark mode and be more professional") == [
        SettingsChange("appearance", "dark")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "write a professional email",
        "explain dark matter",
        "tell me a funny story",
        "draft a casual message to mom",
        "Is the pro model worth it?",
        "dark mode vs light mode — which is better for your eyes?",
        "should I use dark mode at night?",
        "light mode or dark mode for reading at night?",
        "the light mode on my phone hurts my eyes",
        "make the email's tone more formal",
    ],
)
def test_questions_and_content_requests_are_not_settings(text: str) -> None:
    assert extract_settings_changes(text) == []


def test_a_theme_line_after_a_reply_still_switches_the_theme() -> None:
    prior = "Happy 60th birthday, Dad! Thank you for everything you do."
    assert extract_settings_changes("switch it to dark mode", prior_assistant=prior) == [
        SettingsChange("appearance", "dark")
    ]
