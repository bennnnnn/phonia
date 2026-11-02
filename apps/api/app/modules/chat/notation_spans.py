"""Chemical notation in prose stays as written: a SMILES string becomes inline code.

"CN1C=NC2=C1C(=O)N(C(=O)N2C)C" read as an a=b=c chain ("$CN1C = NC2$" rows) on
the server, and as maths ("C $=O$ N") on the phone. As inline code, every later
pass on both sides leaves it alone, and it reads as notation.

A token is notation when it is one unbroken run of SMILES characters whose
letters are all atom symbols, with a bond ("=", "#") or a branch ("(", "[")
and either a branch or a repeated ring closure ("c1 … c1"). Words, equations
("F=ma", "x=2y+1"), links and code identifiers fail the atom-symbol test.
Twin: apps/mobile/lib/markdown/notationSpans.ts, held to the same output by
docs/fixtures/presentation_cases.json.
"""

from __future__ import annotations

import re

from app.modules.chat.markdown_regions import map_prose_outside_fences

_CHARSET = re.compile(r"[A-Za-z0-9@+\-\[\]()=#%/\\.]+")
_LETTERS = re.compile(r"[A-Za-z]+")
# Organic atoms, aromatic lowercase atoms, and two-letter element symbols.
_ATOMS = re.compile(r"(?:Cl|Br|[A-Z][a-z]|[BCNOPSFIKH]|[bcnops])+")
_RING_ATOM = re.compile(r"(?:[A-Z][a-z]?|[cnosp])(\d)")
# Inline code and maths are left as they are; prose between them is read.
_PROTECTED = re.compile(r"(`+[^`\n]*`+|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)")
_TOKEN = re.compile(r"[^\s`$]+")
_TRAILING = ".,;:!?"
_MIN_LENGTH = 6


def is_notation(token: str) -> bool:
    """True for a SMILES string such as ``CC(=O)O`` or ``O=Cc1ccccc1``."""
    if len(token) < _MIN_LENGTH or "://" in token or "](" in token:
        return False
    if not _CHARSET.fullmatch(token):
        return False
    runs = _LETTERS.findall(token)
    # "2(1.008)" has no atom at all; "F=ma" has a run that is not one.
    if not runs or any(not _ATOMS.fullmatch(run) for run in runs):
        return False
    rings = [match.group(1) for match in _RING_ATOM.finditer(token)]
    branched = "(" in token or "[" in token
    bonded = "=" in token or "#" in token
    return (bonded or branched) and (branched or len(rings) > len(set(rings)))


def _code_token(match: re.Match[str]) -> str:
    raw = match.group(0)
    token = raw.rstrip(_TRAILING)
    if not is_notation(token):
        return raw
    return f"`{token}`{raw[len(token) :]}"


def _code_prose(prose: str) -> str:
    parts = _PROTECTED.split(prose)
    # split() keeps the protected spans at odd indexes.
    return "".join(
        part if index % 2 else _TOKEN.sub(_code_token, part) for index, part in enumerate(parts)
    )


def code_notation(text: str) -> str:
    """Wrap each SMILES string in prose as inline code; fences, code and maths stay."""
    if not text or ("=" not in text and "(" not in text and "#" not in text):
        return text
    return map_prose_outside_fences(text, _code_prose)
