"""JSON the user asked for: a prompt hint on those turns, and a check of what came back.

``is_json_request`` reads the user's own words. Only an explicit ask for JSON
output counts ("list the planets as valid JSON", "return a JSON object with ...");
a question about JSON ("how are dates stored in JSON?") or a request for code that
handles it ("write a function that parses JSON") does not.

The finalize pass parses each ```json fence (or a reply that is JSON from its first
character). Malformed JSON gets one cheap repair: trailing commas, a stray fence
line, curly quotes. If that parses, the fence holds the repaired JSON; if not, a
short visible note says it did not validate. Malformed JSON never passes silently.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from app.gateways.model_output import CURLY_QUOTES, TRAILING_COMMA
from app.services.md_fence_scan import iter_closed_fences, read_fence_marker

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

logger = logging.getLogger(__name__)

JSON_OUTPUT_HINT = (
    "The user asked for JSON. Put it in one ```json fence as strict JSON: double-quoted "
    "keys and strings, no comments, no trailing commas, no ... placeholders. Keep any "
    "explanation outside the fence, in one or two short lines."
)
JSON_INVALID_NOTE = "*This JSON didn't pass a validity check, so check it before you use it.*"

# An output verb, then "as/in/into JSON", "valid JSON" or "JSON only/object/array/format"
# in the same clause.
_JSON_OUTPUT = re.compile(
    r"\b(?:give|return|output|respond|reply|answer|format|convert|turn|write|generate"
    r"|produce|list|show|send|provide|make|put|export|dump|create)\b[^.?!\n]{0,80}?"
    r"(?:\b(?:as|in|into|to|with)\s+(?:a\s+|an\s+)?(?:valid\s+|strict\s+|raw\s+|plain\s+)?json\b"
    r"|\bvalid json\b|\bjson\s+(?:only|output|object|array|format)\b)"
    r"|\b(?:only|just)\s+(?:with\s+)?(?:valid\s+)?json\b",
    re.IGNORECASE,
)
# The JSON is what the code handles, not what the reply is.
_CODE_ASK = re.compile(
    r"\b(?:code|function|script|program|python|javascript|typescript|java|serializ\w*"
    r"|deserializ\w*|pars(?:e|es|ing|er)|library|module|regex|endpoint)\b",
    re.IGNORECASE,
)


def is_json_request(text: str | None) -> bool:
    """True when the user asks for the reply itself in JSON."""
    if not text:
        return False
    return _JSON_OUTPUT.search(text) is not None and _CODE_ASK.search(text) is None


def _parses(body: str) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


def repair_json(body: str) -> str | None:
    """The body as valid JSON after one cheap repair, or None when that is not enough."""
    lines = [line for line in body.splitlines() if read_fence_marker(line, lenient=True) is None]
    candidate = TRAILING_COMMA.sub(r"\1", "\n".join(lines).translate(CURLY_QUOTES)).strip()
    try:
        data = json.loads(candidate)
    except ValueError:
        return None
    return json.dumps(data, indent=2, ensure_ascii=False)


def check_json_reply(text: str) -> tuple[str, bool]:
    """The reply with each JSON block valid or repaired, and whether one stayed invalid."""
    pieces: list[str] = []
    cursor = 0
    invalid = False
    found = False
    for start, end, body in iter_closed_fences(text, "json"):
        found = True
        pieces.append(text[cursor:start])
        cursor = end
        if _parses(body):
            pieces.append(text[start:end])
            continue
        repaired = repair_json(body)
        if repaired is None:
            invalid = True
            pieces.append(text[start:end])
        else:
            tail = "\n" if text[start:end].endswith("\n") else ""
            pieces.append(f"```json\n{repaired}\n```{tail}")
    pieces.append(text[cursor:])
    if found:
        return "".join(pieces), invalid
    stripped = text.strip()
    if not stripped.startswith(("{", "[")) or _parses(stripped):
        return text, False
    repaired = repair_json(stripped)
    return (text, True) if repaired is None else (repaired, False)


def check_requested_json(state: FinalizeState) -> str:
    """Finalize pass: on a turn that asked for JSON, the JSON in the reply parses."""
    if state.server_text or state.was_cancelled:
        return state.text
    if not is_json_request(state.ctx.user_message_content):
        return state.text
    text, invalid = check_json_reply(state.text)
    if not invalid:
        return text
    logger.warning("Requested JSON reply did not validate model=%s", state.ctx.model)
    return f"{text.rstrip()}\n\n{JSON_INVALID_NOTE}"
