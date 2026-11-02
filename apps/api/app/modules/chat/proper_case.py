"""Capitals that carry meaning, put back when a casual reply wrote them lowercase.

The casual tone ("like texting a smart friend") read to the free model as lowercase writing
(2026-10-24): "2h₂ + o₂ → 2h₂o", "0 k", "10°c". In chemistry and units a capital is
meaning, not style: h₂o is not a formula. Only that is changed: a formula with subscripts
(rebuilt from element symbols, so fe₂o₃ is Fe₂O₃ and co₂ is CO₂), a degree sign's C or F,
and a kelvin K after a number in a reply about kelvin. Code, maths, quotes, links, paths
and a reply that is bare JSON are left as written.

A subscript is not always chemistry: p₁v₁ = p₂v₂, n₁ sin θ₁ = n₂ sin θ₂, (h₂, k₂) and
"height h₂" are variables. A formula never writes ₁ or ₀, and a letter written with ₁
anywhere in the reply is a variable in its ₂ form too. A lone element (h₂, n₂) or a
product of single letters with one subscript (p₂v₂, h₂o₂) is read as chemistry only
beside a compound that can be nothing else (h₂o, co₂, c₆h₁₂o₆).
"""

from __future__ import annotations

import re
from functools import cache

from app.services.md_fence_scan import iter_fences

_SINGLE = frozenset("hbcnofpskvyiwu")
_DOUBLE = frozenset(
    "he li be ne na mg al si cl ar ca sc ti cr mn fe co ni cu zn ga ge as se br kr rb sr zr nb "
    "mo tc ru rh pd ag cd in sn sb te xe cs ba la ce pr nd pm sm eu gd tb dy ho er tm yb lu hf "
    "ta re os ir pt au hg tl pb bi po at rn fr ra ac th pa np pu am cm bk cf es fm md no lr".split()
)
# Two-letter symbols that beat the one-letter split: SiO₂ not SIO₂, CuSO₄ not CUSO₄. CO₂,
# NO₂, HF and PO₄ split.
_PREFERRED = frozenset({"si", "cu", "pb", "sn", "ni", "sb"})
_MOLECULES = frozenset({"h₂", "o₂", "n₂", "cl₂", "f₂", "br₂", "i₂", "o₃", "p₄", "s₈"})
_SUB = "₀₁₂₃₄₅₆₇₈₉"
_SUBS = re.compile(f"[{_SUB}]+")
_TOKEN = re.compile(f"([a-z]+)([{_SUB}]*)")
_PART = re.compile(f"([{_SUB}()]+)")
# A letter indexed ₁ or ₀ anywhere ("p₁", "n₁") is a variable wherever it appears.
_INDEXED = re.compile(f"(?<![A-Za-z])([A-Za-z]+)[₀₁](?![{_SUB}])")
# A lowercase word that may be a formula: letters, subscript digits and brackets, read by
# ``_read``. One flat class, so a long word cannot backtrack.
_FORMULA = re.compile(rf"(?<![\w$\\])(\d*)([a-z(][a-z(){_SUB}]*)")
# No element run in a formula is longer than this ("mgcl", "nahco"); a longer word is prose.
_MAX_RUN = 8
_DEGREE = re.compile(r"°([cf])\b")
# "0 k", "273 k": a unit after a spaced number, not "2k + 1" or "2 k + 1".
_KELVIN = re.compile(r"(\d)(\s)k\b(?![\w'])(?!\s*[-+*/=^])")
# Left exactly as written: code, maths, quotes, links, paths, emails.
_KEPT = re.compile(
    r"`[^`\n]*`|\$\$.*?\$\$|\$[^$\n]*\$|\\\(.*?\\\)|\\\[.*?\\\]"
    r"|\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d|\u2018[^\u2019\n]*\u2019|(?<!\w)'[^'\n]{1,80}'(?!\w)"
    r"|(?<!\S)[^\s/@\\]*[/@\\]\S*|\bwww\.\S+",
    re.DOTALL,
)


@cache
def _elements(letters: str) -> tuple[str, ...] | None:
    """``letters`` as element symbols, single letters first ("co" is C O); None if not."""
    if not letters:
        return ()
    if letters[:2] in _PREFERRED and (rest := _elements(letters[2:])) is not None:
        return (letters[:2].capitalize(), *rest)
    if letters[0] in _SINGLE and (rest := _elements(letters[1:])) is not None:
        return (letters[0].upper(), *rest)
    if letters[:2] in _DOUBLE and (rest := _elements(letters[2:])) is not None:
        return (letters[:2].capitalize(), *rest)
    return None


def _read(body: str, indexed: frozenset[str]) -> tuple[str, bool] | None:
    """``body`` capitalized, and whether it can only be chemistry; None if no formula."""
    runs = _SUBS.findall(body)
    if not runs or any(run in ("₀", "₁") for run in runs):
        return None
    tokens = _TOKEN.findall(body)
    if any(sub and letters in indexed for letters, sub in tokens):
        return None
    out: list[str] = []
    symbols: list[str] = []
    for part in _PART.split(body):
        if not part or not part.isalpha():
            out.append(part)
            continue
        found = _elements(part) if len(part) <= _MAX_RUN else None
        if found is None:
            return None
        symbols.extend(found)
        out.append("".join(found))
    if len(symbols) == 1 and body.strip("()") not in _MOLECULES:
        return None
    # "p₂v₂", "h₂", "n₂": as much a variable as a molecule.
    uniform = all(len(letters) == 1 and sub for letters, sub in tokens) and len(set(runs)) == 1
    return "".join(out), len(symbols) > 1 and not uniform


def _formulas(text: str, indexed: frozenset[str], chemistry: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        read = _read(match.group(2), indexed)
        if read is None or not (read[1] or chemistry):
            return match.group(0)
        return match.group(1) + read[0]

    return _FORMULA.sub(replace, text)


def _has_compound(text: str, indexed: frozenset[str]) -> bool:
    """Whether ``text`` holds a formula that can be nothing but chemistry."""
    for match in _FORMULA.finditer(text):
        read = _read(match.group(2), indexed)
        if read is not None and read[1]:
            return True
    return False


def _prose(text: str, kelvin: bool, indexed: frozenset[str], chemistry: bool) -> str:
    text = _formulas(text, indexed, chemistry)
    text = _DEGREE.sub(lambda m: "°" + m.group(1).upper(), text)
    if kelvin:
        text = _KELVIN.sub(lambda m: f"{m.group(1)}{m.group(2)}K", text)
    return text


def _outside_kept(text: str, kelvin: bool, indexed: frozenset[str], chemistry: bool) -> str:
    pieces, at = [], 0
    for span in _KEPT.finditer(text):
        pieces.append(_prose(text[at : span.start()], kelvin, indexed, chemistry))
        pieces.append(span.group(0))
        at = span.end()
    pieces.append(_prose(text[at:], kelvin, indexed, chemistry))
    return "".join(pieces)


def restore_proper_case(text: str) -> str:
    """The reply with formulas and units capitalized; fences, code and quotes kept."""
    if text.lstrip().startswith(("{", "[")):
        return text  # a bare JSON reply is data the user asked for
    kelvin = "kelvin" in text.casefold()
    indexed = frozenset(letters.casefold() for letters in _INDEXED.findall(text))
    chemistry = _has_compound(_KEPT.sub(" ", text), indexed)
    pieces, at = [], 0
    for fence in iter_fences(text):
        pieces.append(_outside_kept(text[at : fence.start], kelvin, indexed, chemistry))
        body = text[fence.start : fence.end]
        # A plain fence the model put a formula in is prose: "2h₂ + o₂ → 2h₂o".
        pieces.append(_formulas(body, indexed, chemistry) if not fence.lang else body)
        at = fence.end
    pieces.append(_outside_kept(text[at:], kelvin, indexed, chemistry))
    return "".join(pieces)
