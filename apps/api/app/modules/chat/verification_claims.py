"""The model's own claims that a result was verified, taken out of an unverified reply.

Only the server's card says a result was checked; prose that says so on a turn the
server did not verify would fake the check mark.
"""

from __future__ import annotations

import re

from app.services.answer_fence import map_outside_fences

_CHECK_MARKS = "✅✔☑✓"  # ✅ ✔ ☑ ✓
_CLAIM_VERB = r"(?:verified|checked|confirmed|double[- ]checked)"
_CHECKER = (
    r"(?:sympy|sym\s*py|the\s+(?:symbolic\s+)?solver|a\s+(?:symbolic\s+)?solver|"
    r"the\s+(?:symbolic\s+|math\s+)+engine|a\s+(?:symbolic\s+)?(?:math\s+)?engine|"
    r"symbolic\s+(?:math|algebra)|a\s+computer\s+algebra\s+system|a\s+cas|"
    r"the\s+cas|the\s+server|the\s+app)"
)
# ✅ Verified with SymPy. / ✓ Checked, ending its sentence or line: "✅ Checked in online" stays.
_EMOJI_CLAIM = re.compile(
    rf"[ \t]*[{_CHECK_MARKS}]️?[ \t]*(?:\*\*|__|\*|_)?[ \t]*{_CLAIM_VERB}\b(?:[ \t]+(?:"
    rf"(?:with|by|using|via|in)[ \t]+{_CHECKER}|(?:with|using|via)[ \t]+[A-Za-z][\w.-]*))?"
    r"[ \t]*(?:\*\*|__|\*|_)?[ \t]*(?:[.!](?:\*\*|__|\*|_)?(?=\s|$)|(?=[ \t]*(?:\n|$)))",
    re.IGNORECASE,
)
# (verified) / (verified with SymPy) / [checked]
_PAREN_CLAIM = re.compile(
    rf"[ \t]*[(\[][ \t]*[{_CHECK_MARKS}]?️?[ \t]*{_CLAIM_VERB}"
    r"(?:[ \t]+(?:with|by|using|via|in)[ \t]+[^)\]\n]{1,40})?[ \t]*[)\]]",
    re.IGNORECASE,
)
# A sentence that says a solver checked the result: "This was verified by the solver."
_SENTENCE_CLAIM = re.compile(
    rf"(?:(?<=^)|(?<=[.!?\n])[ \t]*)[^.!?\n]*\b{_CLAIM_VERB}[ \t]+(?:with|by|using|via|in)[ \t]+"
    rf"{_CHECKER}\b[^.!?\n]*[.!]?",
    re.IGNORECASE,
)
# A "Verified answer:" / "**Verified result:**" label opening a line keeps its job
# as a label and loses the claim. Mid-sentence wording is left alone.
_LABEL_CLAIM = re.compile(
    r"^(?P<lead>[ \t>]*(?:\*\*|__)?[ \t]*)verified[ \t]+(?P<noun>answer|result|solution)"
    r"(?=[ \t]*(?:\*\*|__)?[ \t]*:)",
    re.IGNORECASE | re.MULTILINE,
)


def _claimless(prose: str) -> str:
    out = _EMOJI_CLAIM.sub("", prose)
    out = _PAREN_CLAIM.sub("", out)
    out = _SENTENCE_CLAIM.sub("", out)
    out = _LABEL_CLAIM.sub(
        lambda match: f"{match.group('lead') or ''}{match.group('noun').capitalize()}", out
    )
    out = re.sub(r"[ \t]+\n", "\n", out)
    return re.sub(r"\n{3,}", "\n\n", out)


def strip_verification_claims(text: str) -> str:
    """Remove the model's own "verified" claims from prose (fences untouched).

    Only for a turn the server did not verify: there the check mark is absent
    by design, and text that says otherwise would fake it.
    """
    lower = text.lower()
    if not any(word in lower for word in ("verif", "checked", "confirmed")):
        return text
    return map_outside_fences(text, _claimless).strip()
