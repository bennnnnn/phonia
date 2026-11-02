"""On a searched turn a claim the sources never made is cut before the reply saves.

A study chat (2026-10-26) had a reply say a broker "has been reinstated and is fully
operational, so you can use them safely" under sources that said nothing of the kind, and a
fee table with a "CSTA levy" no source named. The model is stubbed here; what is held is what
the pass does with its verdict: it cuts only what the reply says word for word, never
outside prose, never most of a reply, and never costs the user an answer.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.chat import claim_check
from app.modules.chat.claim_check import cut_unsupported_claims
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext

_HITS = [
    WebSearchHit(
        title="Hustlelife",
        url="https://hustlelife.example/nse",
        snippet="Brokerage (2%): KSh 1,000\nNSE levy: KSh 60\nCMA levy: KSh 25\nCDSC fee: KSh 90",
    )
]
_TABLE = (
    "| Charge | Rate | Cost (KES) |\n"
    "| :--- | :--- | :--- |\n"
    "| NSE levy | 0.12% | 36 |\n"
    "| CSTA Levy | 0.5% | 150 |\n"
    "| CDSC fee | flat | 90 |"
)
_REPLY = f"Here is the fee breakdown for a 30,000 KES purchase.\n\n{_TABLE}\n\nCytonn has been reinstated and is fully operational, so you can use them safely. Compare brokers before you pick one."


def _state(reply: str = _REPLY, **ctx_fields: Any) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="qwen-3.7-flash",
        prompt_messages=[
            {"role": "user", "content": "I earn 80,000 KES a month"},
            {"role": "assistant", "content": "Aka Capital pools T-bills from KES 3,000."},
            {"role": "user", "content": "what fees on 30,000?"},
        ],
        run_title=False,
        user_message_content="what fees on 30,000?",
        reserved_tokens=0,
        max_output_tokens=0,
        search_sources=list(_HITS),
    )
    for name, value in ctx_fields.items():
        setattr(ctx, name, value)
    return FinalizeState(
        deps=None,  # type: ignore[arg-type]  # this pass reads no dependency
        settings=Settings(),
        ctx=ctx,
        raw=reply,
        text=reply,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[reply],
        should_cancel=None,
    )


def _verdict(*quotes: str, note: str = "") -> claim_check._Verdict:
    return claim_check._Verdict(
        unsupported=[claim_check._Claim(quote=q, topic="a levy") for q in quotes],
        note=note,
    )


def _ask(verdict: claim_check._Verdict | None) -> AsyncMock:
    return AsyncMock(return_value=verdict)


async def _run(state: FinalizeState, verdict: claim_check._Verdict | None) -> str:
    with patch.object(claim_check, "complete_structured", _ask(verdict)):
        return await cut_unsupported_claims(state)


async def test_an_unsupported_table_row_and_sentence_are_cut_and_the_rest_kept() -> None:
    out = await _run(
        _state(),
        _verdict(
            "| CSTA Levy | 0.5% | 150 |",
            "Cytonn has been reinstated and is fully operational, so you can use them safely.",
            note="I couldn't confirm two details from the sources, so I left them out.",
        ),
    )
    assert "CSTA" not in out
    assert "Cytonn" not in out
    assert "| NSE levy | 0.12% | 36 |" in out
    assert "| CDSC fee | flat | 90 |" in out
    assert "Compare brokers before you pick one." in out
    assert out.rstrip().endswith(
        "*I couldn't confirm two details from the sources, so I left them out.*"
    )


async def test_a_quote_inside_a_sentence_cuts_that_sentence_only() -> None:
    reply = "Brokers charge about 2% on a trade (see the source). The CMA licenses Cytonn as of October 2026. Ask each broker for its own rate before buying."
    out = await _run(_state(reply), _verdict("licenses Cytonn as of October 2026"))
    assert "Cytonn" not in out
    assert out.startswith("Brokers charge about 2% on a trade (see the source). Ask each broker")


async def test_a_quote_the_reply_never_wrote_cuts_nothing() -> None:
    out = await _run(_state(), _verdict("Savannah Securities charges 1%"))
    assert out == _REPLY


async def test_a_quote_in_a_code_fence_is_left_alone() -> None:
    reply = f"Here is the rate table you asked for, kept as written below.\n\n```text\nCSTA levy 0.5%\n```\n\n{_TABLE}"
    out = await _run(_state(reply), _verdict("CSTA levy 0.5%"))
    assert "CSTA levy 0.5%" in out


async def test_a_table_with_every_row_cut_loses_its_header_too() -> None:
    table = "| Fee | Rate |\n| :--- | :--- |\n| CSTA | 0.5% |\n| CASS | 0.075% |"
    reply = f"These are the charges that apply to a purchase on the exchange today.\n\n{table}\n\nAsk your broker for the final amount."
    out = await _run(_state(reply), _verdict("| CSTA | 0.5% |", "| CASS | 0.075% |"))
    assert "|" not in out
    assert "Ask your broker for the final amount." in out


async def test_a_tables_total_goes_with_a_row_cut_from_it() -> None:
    table = (
        "| Charge | Rate | Cost |\n| :--- | :--- | :--- |\n| Levy | 0.12% | 36 |\n"
        "| **Stamp Duty** | ~0.5%* | 150 |\n| **Total** | **~1.98%** | **594** |"
    )
    reply = f"The charges on a 30,000 KES purchase are below, with each in shillings.\n\n{table}\n\nAsk your broker."
    out = await _run(_state(reply), _verdict("Stamp duty ~0.5% 150"))
    assert "| Levy | 0.12% | 36 |" in out
    assert "Stamp" not in out
    assert "Total" not in out


async def test_a_total_is_kept_when_no_row_was_cut() -> None:
    table = "| Charge | Cost |\n| :--- | :--- |\n| Levy | 36 |\n| Fee | 90 |\n| Total | 126 |"
    reply = f"The charges on a 30,000 KES purchase are below, with each in shillings.\n\n{table}\n\nAsk your broker for the final amount before you buy."
    out = await _run(_state(reply), _verdict("Cytonn is reinstated"))
    assert "| Total | 126 |" in out


async def test_a_quote_retyped_without_its_markdown_still_finds_its_line() -> None:
    reply = "The brokerage is 1.14% of the trade, as the Ziidi page lists it for retail clients.\n\n**Standard stamp duty is roughly 0.5% of the trade value.**\n\nAsk your broker for the final amount before you buy."
    out = await _run(
        _state(reply), _verdict("Standard stamp duty is roughly 0.5% of the trade value.")
    )
    assert "stamp duty" not in out
    assert "1.14%" in out


async def test_blank_lines_between_paragraphs_survive_a_cut() -> None:
    reply = "First paragraph with enough words to be a real answer here.\n\nSecond has the bad claim: Cytonn is reinstated.\n\nThird paragraph stays exactly as it was written."
    out = await _run(_state(reply), _verdict("Cytonn is reinstated."))
    assert "First paragraph" in out
    assert "\n\nThird paragraph stays exactly as it was written." in out


async def test_a_check_that_flags_most_of_the_reply_changes_nothing() -> None:
    reply = "Cytonn is fully licensed and reinstated by the CMA as of October 2026 for everything it does."
    out = await _run(_state(reply), _verdict(reply))
    assert out == reply


@pytest.mark.parametrize(
    "verdict",
    [None, claim_check._Verdict(), claim_check._Verdict(note="all fine")],
)
async def test_no_verdict_or_nothing_flagged_leaves_the_reply_whole(
    verdict: claim_check._Verdict | None,
) -> None:
    assert await _run(_state(), verdict) == _REPLY


@pytest.mark.parametrize(
    "state",
    [
        _state(search_sources=[]),
        _state(instant_reply="Server text only, not worth checking at all, it is long enough."),
        _state("Short."),
    ],
)
async def test_turns_without_a_search_or_with_server_text_never_ask_the_model(
    state: FinalizeState,
) -> None:
    ask = _ask(_verdict("anything"))
    with patch.object(claim_check, "complete_structured", ask):
        out = await cut_unsupported_claims(state)
    assert out == state.raw
    ask.assert_not_awaited()


@pytest.mark.parametrize("field", ["verified_subject", "money"])
async def test_a_turn_with_a_verified_result_or_money_card_is_not_checked(field: str) -> None:
    ask = _ask(_verdict("x" * 5))
    state = _state()
    setattr(state.ctx, field, object())
    with patch.object(claim_check, "complete_structured", ask):
        await cut_unsupported_claims(state)
    ask.assert_not_awaited()


async def test_the_setting_turns_the_check_off() -> None:
    state = _state()
    state.settings = Settings(claim_check_enabled=False)
    ask = _ask(_verdict("CSTA Levy"))
    with patch.object(claim_check, "complete_structured", ask):
        assert await cut_unsupported_claims(state) == _REPLY
    ask.assert_not_awaited()


async def test_the_model_sees_the_sources_and_the_users_words_but_not_earlier_replies() -> None:
    ask = _ask(None)
    with patch.object(claim_check, "complete_structured", ask):
        await cut_unsupported_claims(_state())
    assert ask.await_args is not None
    prompt = ask.await_args.kwargs["messages"][1]["content"]
    assert "NSE levy: KSh 60" in prompt
    assert "I earn 80,000 KES a month" in prompt
    assert "what fees on 30,000?" in prompt
    assert "Aka Capital pools T-bills" not in prompt
    assert "ASSISTANT REPLY TO CHECK" in prompt


def test_the_checker_is_told_a_headline_is_evidence() -> None:
    # A reply citing a result's headline was once cut as unsupported: the verifier read
    # only the text under it.
    assert claim_check.HEADLINE_IS_EVIDENCE in claim_check._SYSTEM


async def test_the_default_note_names_what_was_left_out() -> None:
    out = await _run(_state(), _verdict("| CSTA Levy | 0.5% | 150 |"))
    assert out.rstrip().endswith("left them out: a levy.*")


_LEAD = "The charges on a 30,000 KES purchase are listed below, with each in shillings.\n\n"


async def test_a_cut_header_takes_its_whole_table_not_just_the_title() -> None:
    reply = f"{_LEAD}| Fee | Rate |\n|---|---|\n| Brokerage | 1.2% |\n| Levy | 0.12% |\n\nAsk your broker for the final amount."
    out = await _run(_state(reply), _verdict("| Fee | Rate |"))
    assert "---" not in out
    assert "Brokerage" not in out


async def test_a_cut_line_between_two_tables_leaves_each_table_alone() -> None:
    a = "| A | Cost |\n|---|---|\n| One | 1 |\n| Total | 1 |"
    b = "| B | Cost |\n|---|---|\n| Two | 2 |\n| Total | 2 |"
    reply = f"{_LEAD}{a}\nNote: the levy is 5%.\n{b}\n\nAsk your broker."
    out = await _run(_state(reply), _verdict("Note: the levy is 5%."))
    assert "| Total | 1 |" in out
    assert "| Total | 2 |" in out
    assert "5%" not in out


async def test_a_table_the_cut_did_not_touch_is_left_as_written() -> None:
    header_only = "| Fee | Rate |\n|---|---|"
    reply = f"{_LEAD}{header_only}\n\nBad claim here: Cytonn is reinstated.\n\nAsk your broker."
    out = await _run(_state(reply), _verdict("Bad claim here: Cytonn is reinstated."))
    assert header_only in out


async def test_a_bullet_keeps_its_marker_when_its_first_sentence_is_cut() -> None:
    reply = (
        f"{_LEAD}- Costs $5 a month. Next thing to know is here.\n- Another point stays as it was."
    )
    out = await _run(_state(reply), _verdict("Costs $5 a month."))
    assert "- Next thing to know is here." in out
    assert "- Another point stays" in out


async def test_a_quote_that_names_no_single_sentence_cuts_and_says_nothing() -> None:
    reply = f"{_LEAD}Brokerage fee is 1.2% of value. The levy is 0.12%. Ask your broker today."
    out = await _run(_state(reply), _verdict("Brokerage fee 1.5% of value"))
    assert out == reply


async def test_a_short_quote_is_not_found_inside_a_longer_figure() -> None:
    reply = f"{_LEAD}Other is 10.5%. The levy is 0.5%. Ask your broker for the final amount."
    out = await _run(_state(reply), _verdict("0.5%"))
    assert "Other is 10.5%." in out
    assert "The levy is 0.5%." not in out


async def test_a_retyped_quote_with_another_figure_does_not_cut_a_sibling_row() -> None:
    table = "| Charge | Rate |\n|---|---|\n| Brokerage fee | 1.2% |\n| Levy | 0.12% |"
    reply = f"{_LEAD}{table}\n\nAsk your broker for the final amount."
    out = await _run(_state(reply), _verdict("Brokerage fee 1.5%"))
    assert "| Brokerage fee | 1.2% |" in out


async def test_what_the_user_asked_us_to_remember_is_evidence() -> None:
    state = _state()
    state.ctx.memory_hints = ["Works at Safaricom as an engineer"]
    ask = _ask(None)
    with patch.object(claim_check, "complete_structured", ask):
        await cut_unsupported_claims(state)
    assert ask.await_args is not None
    assert "Works at Safaricom" in ask.await_args.kwargs["messages"][1]["content"]


_STEPS = (
    "1. The NSE levy is 0.12% of the trade value.\n"
    "2. The CSTA levy is 0.5% of the trade value.\n"
    "3. The CDSC fee is a flat 90 shillings.\n"
    "4. Brokerage is about 2% at most brokers."
)


@pytest.mark.parametrize(
    ("quote", "kept"),
    [
        # Live (2026-10-29): item 1 went and the list started at 2.
        (
            "The NSE levy is 0.12% of the trade value.",
            ["1. The CSTA", "2. The CDSC", "3. Brokerage"],
        ),
        (
            "The CSTA levy is 0.5% of the trade value.",
            ["1. The NSE", "2. The CDSC", "3. Brokerage"],
        ),
    ],
)
async def test_a_numbered_list_that_lost_an_item_counts_on(quote: str, kept: list[str]) -> None:
    out = await _run(
        _state(f"{_LEAD}{_STEPS}\n\nAsk your broker for the final amount."), _verdict(quote)
    )
    numbered = [
        line[: len(start)]
        for line in out.splitlines()
        for start in kept
        if line.startswith(start[:3])
    ]
    assert numbered == kept


async def test_a_list_that_lost_nothing_keeps_its_numbers() -> None:
    reply = f"{_LEAD}{_STEPS}\n\nThen, at settlement:\n\n5. Pay within three days.\n6. Keep the contract note."
    out = await _run(_state(reply), _verdict("The CSTA levy is 0.5% of the trade value."))
    assert "5. Pay within three days.\n6. Keep the contract note." in out
    assert "3. Brokerage is about 2% at most brokers." in out


async def test_a_nested_list_does_not_end_the_outer_count() -> None:
    reply = (
        f"{_LEAD}1. The NSE levy is 0.12% of the trade value.\n"
        "2. The CSTA levy is 0.5% of the trade value.\n"
        "   1. It is charged on both sides of the trade.\n"
        "3. The CDSC fee is a flat 90 shillings.\n"
        "4. Brokerage is about 2% at most brokers."
    )
    out = await _run(_state(reply), _verdict("The NSE levy is 0.12% of the trade value."))
    assert "1. The CSTA levy" in out
    assert "   1. It is charged on both sides" in out
    assert "2. The CDSC fee" in out
    assert "3. Brokerage is about 2%" in out


async def test_a_list_numbered_with_brackets_counts_on_too() -> None:
    reply = f"{_LEAD}{_STEPS.replace('. ', ') ', 4)}\n\nAsk your broker."
    out = await _run(_state(reply), _verdict("The CSTA levy is 0.5% of the trade value."))
    assert "2) The CDSC fee" in out and "3) Brokerage" in out
