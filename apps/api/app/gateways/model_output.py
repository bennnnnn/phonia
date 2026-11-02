"""Reading what a model wrote: the fence it wraps replies in, and the JSON inside.

One reader for every caller: the structured-output gateway, the maths photo extract,
the scan read and OCR's page text each unwrapped the fence their own way, and only one
escaped the LaTeX a model writes unescaped inside a JSON string (code-health audit
DUP-04). Pure text functions, light enough for any module to import.
"""

from __future__ import annotations

import json
import re

# LaTeX commands that begin with a JSON escape letter: `\text` must not decode as a tab.
_LATEX_ON_JSON_ESCAPES = frozenset(
    {
        *("bar", "begin", "beta", "binom", "bmod", "boxed"),
        *("forall", "frac"),
        *("nabla", "ne", "neg", "neq", "nexists", "ngeq", "ni", "nleq", "nmid", "not", "notin"),
        "nu",
        *("rangle", "rceil", "rfloor", "rho", "right", "rightarrow"),
        *("tan", "tanh", "tau", "text", "textbf", "textit", "textrm", "tfrac", "theta"),
        *("tilde", "times", "triangle"),
    }
)


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def escape_latex_in_json(raw: str) -> str:
    """Double the backslash of a LaTeX command a model wrote unescaped in a JSON string.

    Written with one backslash, `$15\\text{ cm}$` decoded `\\t` as a tab (a follow-up read
    "15 ext{ cm}"), `\\frac` as a form feed, and `\\alpha` is no JSON escape at all, so the
    whole output failed to parse. A real escape (`\\n`, `\\"`, `\\\\`, `\\u00e9`) is kept.
    """
    out: list[str] = []
    i = 0
    # Inside a $…$ span a backslash, t, f, b or r and letters is a command, listed or not
    # ("$30^\\textdegree$" read as a tab and "extdegree"); a JSON string's quote ends it.
    in_math = False
    while i < len(raw):
        if raw[i] in '$"':
            in_math = not in_math if raw[i] == "$" else False
        if raw[i] != "\\" or i + 1 == len(raw):
            out.append(raw[i])
            i += 1
            continue
        after = raw[i + 1]
        if after in '"\\/':
            out.append(raw[i : i + 2])
            i += 2
            continue
        if after == "u" and i + 6 <= len(raw) and all(c in _HEX_DIGITS for c in raw[i + 2 : i + 6]):
            out.append(raw[i : i + 6])
            i += 6
            continue
        if after in "bfnrt":
            end = i + 1
            while end < len(raw) and raw[end].isascii() and raw[end].isalpha():
                end += 1
            # "\\n" before letters may be a newline before a word even in a "$5 … $6" span.
            command = in_math and after != "n" and end - i > 2
            if not command and raw[i + 1 : end] not in _LATEX_ON_JSON_ESCAPES:
                out.append(raw[i : i + 2])
                i += 2
                continue
        out.append("\\\\")  # a LaTeX command, or a backslash JSON has no escape for
        i += 1
    return "".join(out)


# A trailing comma before ``}`` or ``]``, and the curly quotes a model sometimes types.
TRAILING_COMMA = re.compile(r",(\s*[}\]])")
CURLY_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"'})


def unwrap_model_fence(raw: str, *tags: str) -> str:
    """A model reply without the code fence it wrapped itself in (```json … ```)."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    parts = text.split("```", 2)
    body = parts[1] if len(parts) > 1 else ""
    for tag in tags:
        if body.startswith(tag):
            body = body[len(tag) :]
            break
    return body.strip()


def parse_model_json(raw: str) -> object:
    """A model's JSON: fence unwrapped, LaTeX backslashes escaped, then one cheap repair
    (trailing commas, curly quotes) when it does not parse. Raises ``ValueError``."""
    text = escape_latex_in_json(unwrap_model_fence(raw, "json"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(TRAILING_COMMA.sub(r"\1", text.translate(CURLY_QUOTES)))
