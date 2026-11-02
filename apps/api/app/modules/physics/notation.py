"""The symbols a reply shows for a law that tells a starting velocity from a final one.

A student writes those velocities $v_i$ and $v_f$: $v_f = v_i + at$, not $v = u + at$.
The catalog and the solvers keep their short letters (``u`` and ``v`` in the
constant-acceleration laws, ``v_1`` and ``v_2`` for before and after an impulse),
because those letters are what the binder, the model reader and the solvers name.
This table is the one place that decides what the reply shows instead: every row a
solver stores (``working.attach_recorded_working``), and every symbol the direct
reply takes from the catalog (the givens, their meanings, Required, the law's own
lines), pass through ``shown``. A law not in the table is shown as written; a plain
speed (``v = d/t``) has no start or end to tell apart.
"""

from __future__ import annotations

from collections.abc import Mapping

# Constant acceleration from a starting velocity u to a final velocity v.
_START_END: Mapping[str, str] = {"u": "v_i", "v": "v_f"}
# One body before and after: an impulse, the work done on it, a bounce off a wall.
_BEFORE_AFTER: Mapping[str, str] = {"v_1": "v_i", "v_2": "v_f"}
# Two bodies colliding: each one's velocity before (v_1, v_2) and after (v_1', v_2').
_TWO_BODIES: Mapping[str, str] = {
    "v_1": "v_{1i}",
    "v_2": "v_{2i}",
    "v_1'": "v_{1f}",
    "v_2'": "v_{2f}",
}
# Braking from a speed v to rest: the speed is where the stop starts.
_BRAKING_FROM: Mapping[str, str] = {"v": "v_i"}

_SHOWN: Mapping[str, Mapping[str, str]] = {
    "suvat_velocity": _START_END,
    "suvat_distance": _START_END,
    "suvat_time": _START_END,
    "suvat_acceleration": _START_END,
    "suvat_initial_velocity": _START_END,
    "average_force_from_speeds": _START_END,
    "energy_speed_from_moving_start": _START_END,
    "impulse": _BEFORE_AFTER,
    "work_energy": _BEFORE_AFTER,
    "momentum_change_rebound": _BEFORE_AFTER,
    "rebound_average_force": _BEFORE_AFTER,
    "final_velocity": _TWO_BODIES,
    "collision_energy_lost": _TWO_BODIES,
    "stopping_distance": _BRAKING_FROM,
}

# Arguments that are words, not symbols: ``\mathrm{m/s}``, ``\text{ before}``.
_WORD_ARGUMENTS = frozenset({"text", "mathrm", "textrm", "operatorname", "mbox"})


def renamed_operations() -> frozenset[str]:
    """The operations whose velocities are shown under another symbol."""
    return frozenset(_SHOWN)


def shown(latex: str, operation: str | None) -> str:
    """``latex`` with this law's velocities written as the reply shows them.

    ``v = u + at`` becomes ``v_f = v_i + at`` and ``ut`` becomes ``v_i t``; a command
    (``\\tau``, ``\\frac``), a word argument (``\\mathrm{m/s}``) and a number are left
    as they are.
    """
    table = _SHOWN.get(operation or "")
    if not table or not latex:
        return latex
    return _rename(latex, table)


def _rename(latex: str, table: Mapping[str, str]) -> str:
    out: list[str] = []
    at = 0
    while at < len(latex):
        char = latex[at]
        if char == "\\":
            end = _command_end(latex, at)
            out.append(latex[at:end])
            at = end
        elif char.isascii() and char.isalpha():
            end = _symbol_end(latex, at)
            symbol = latex[at:end]
            replacement = table.get(_plain(symbol))
            if replacement is None:
                out.append(symbol)
            else:
                out.append(replacement)
                # "ut" is u times t: v_i t, never the subscript "it".
                if "_" in replacement and end < len(latex) and latex[end].isalnum():
                    out.append(" ")
            at = end
        else:
            out.append(char)
            at += 1
    return "".join(out)


def _command_end(latex: str, start: int) -> int:
    """Past a command, and past its argument when that argument is words."""
    end = start + 1
    while end < len(latex) and latex[end].isascii() and latex[end].isalpha():
        end += 1
    if end == start + 1:
        # A one-character command: "\,", "\ ", "\{".
        return min(end + 1, len(latex))
    if latex[start + 1 : end] in _WORD_ARGUMENTS:
        brace = end
        while brace < len(latex) and latex[brace] == " ":
            brace += 1
        if brace < len(latex) and latex[brace] == "{":
            return _group_end(latex, brace)
    return end


def _group_end(latex: str, brace: int) -> int:
    """Past the ``{…}`` group that opens at ``brace``."""
    depth = 0
    for index in range(brace, len(latex)):
        if latex[index] == "{":
            depth += 1
        elif latex[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(latex)


def _symbol_end(latex: str, at: int) -> int:
    """Past one symbol: a letter, its subscript (``_1``, ``_{net}``) and any primes."""
    end = at + 1
    if end < len(latex) and latex[end] == "_":
        if end + 1 < len(latex) and latex[end + 1] == "{":
            end = _group_end(latex, end + 1)
        elif end + 1 < len(latex) and latex[end + 1] != "\\":
            end += 2
    while end < len(latex) and latex[end] == "'":
        end += 1
    return end


def _plain(symbol: str) -> str:
    """``v_{1}'`` and ``v_1'`` are one symbol."""
    head, _, rest = symbol.partition("_")
    if not rest:
        return symbol
    primes = len(rest) - len(rest.rstrip("'"))
    script = rest.rstrip("'")
    if script.startswith("{") and script.endswith("}") and len(script) == 3:
        script = script[1]
    return f"{head}_{script}" + "'" * primes
