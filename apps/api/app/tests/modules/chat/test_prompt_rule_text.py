"""The prompt's rules as one text: what the leak pass checks a reply against.

Structure ticket ST-04 moved the readers out of chat's prompt constants and the chemistry
fence hint into chemistry. Their words stay in the rules, so a reply that copies one is
still caught: the rule strings and the grams each one makes are held to their values
before the move. A change to the prompt's copy changes both; update them with it.
"""

from __future__ import annotations

import hashlib

from app.modules.chat.prompt_leaks import _grams
from app.modules.chat.prompt_rule_text import prompt_rule_text
from app.modules.chemistry.reply_policy import CHEMISTRY_FENCE_HINT

# Distinct rule strings and the 4-grams within each: before ST-04 (main e4c784a5a), then with
# the worked layout's Required heading and its Solve-for step, then with physics'
# PHYSICS_VELOCITY_NOTATION (initial and final velocity written v_i and v_f), then the
# ```worked block's contract (prompt_constants.worked), then the calculation layout's rule
# that multiplication is written \times, never a dot, then the formula headed by its name
# ("Average speed formula", never the name after the formula) and the Solution heading.
_RULES = 164
_RULE_GRAMS = 14419
_RULE_GRAMS_SHA = "496a49bd990e39fc"


def _rules() -> list[str]:
    from app.modules.chat.prompt_rule_text import _rule_sources, _source_rules, _strings
    from app.modules.chat.prompt_subjects import SUBJECT_HINTS

    rules = [rule for source in _rule_sources() for rule in _source_rules(source)]
    for hints in SUBJECT_HINTS.values():
        for short in (False, True):
            rules += _strings(list(hints.presentation(short)))
        rules += _strings(hints.closing)
    return rules


def test_the_rule_text_is_the_rules_joined() -> None:
    assert "\n".join(_rules()) == prompt_rule_text()


def test_the_rules_and_their_grams_are_what_they_were() -> None:
    rules = set(_rules())
    grams = set().union(*(_grams(rule, 4) for rule in rules))
    digest = hashlib.sha256("\n".join(sorted(grams)).encode()).hexdigest()[:16]
    assert (len(rules), len(grams), digest) == (_RULES, _RULE_GRAMS, _RULE_GRAMS_SHA)


def test_the_chemistry_fence_hint_is_still_a_rule() -> None:
    assert CHEMISTRY_FENCE_HINT in prompt_rule_text()


def test_a_readers_word_list_is_still_a_rule() -> None:
    from app.modules.turn_reading.capabilities import _CAPABILITIES_EXACT

    text = prompt_rule_text()
    assert all(phrase in text for phrase in _CAPABILITIES_EXACT if len(phrase) >= 40)


def test_a_reply_copying_the_chemistry_fence_hint_loses_it() -> None:
    from app.modules.chat.prompt_leaks import _rule_grams, drop_prompt_leaks

    reply = (
        "Ethanol is CH3CH2OH.\n\n"
        "Use verified SMILES from the system block verbatim when present.\n\n"
        "Do not emit a molecule card unless this turn is actually about a chemical structure."
    )
    assert drop_prompt_leaks(reply, "what is ethanol?", rules=_rule_grams()) == (
        "Ethanol is CH3CH2OH.\n"
    )
