"""Textbook labels such as ``h0 =`` that look like algebra but only name a given."""

from __future__ import annotations

import re

_PARAM_ASSIGN_RE = re.compile(
    r"\b(?:gravity|theta|angle|h_?0|v_?0|omega|mu|rho|delta|"
    r"[mqxv]_?[12]|[hFmgMRIcRx])\s*=\s*(?=-?\d)",
    re.IGNORECASE,
)


T_ASSIGN_RE = re.compile(r"\bt\s*=\s*(?=-?\d)", re.IGNORECASE)


# A given named in words: "(specific heat capacity = 4200 J/kg C)",
# "refractive index = 1.5", "mass of the Earth = 6 x 10^24 kg". Read as
# algebra, the question was handed to the model.
_NAMED_GIVEN_RE = re.compile(
    r"\b(?:[a-z]+\s+){0,3}(?:capacity|heat|constant|density|index|mass|speed|velocity|"
    r"acceleration|force|charge|resistance|current|voltage|frequency|wavelength|energy|"
    r"power|pressure|volume|temperature|length|radius|height|distance|period|coefficient|"
    r"tension|weight|momentum|area|capacitance|inductance|emf)"
    r"(?:\s+of\s+(?:the\s+)?[a-z]+)?\s*=\s*(?=-?\d)",
    re.IGNORECASE,
)


_NAMED_FORMULA_RE = re.compile(
    r"\b(?:using|from|with)\s+E\s*=\s*m\s*c(?:\^?2|²)\b",
    re.IGNORECASE,
)


def strip_param_assignments(text: str) -> str:
    """Remove textbook labels such as ``h0 =``, ``m1 =``, ``x_2 =`` and
    ``g =`` so has_equation does not mistake a list of givens for algebra.
    The number and unit stay for the quantity scanners.

    Do not strip ``t`` / ``v`` / ``a`` / ``d`` — those are often the unknown
    (``find v when t = 1 s``) and stripping them silently solves the wrong op.
    """
    text = _NAMED_GIVEN_RE.sub("", _NAMED_FORMULA_RE.sub("", text))
    return _PARAM_ASSIGN_RE.sub("", text)
