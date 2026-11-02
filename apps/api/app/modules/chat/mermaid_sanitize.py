"""Quote mermaid node labels that contain raw parentheses.

Unquoted ``E[Grind Beans (Medium Grind)]`` is invalid Mermaid and the
WebView parse-fails. A shape drawn inside the brackets keeps its marks
outside the quotes: the cylinder ``DB[(Database)]`` is left as it is, and
``DB[(Primary (rw))]`` becomes ``DB[("Primary (rw)")]``, not a box labelled
"(Primary (rw))". Linear scan — no nested regex. Twin of the phone's
``lib/mermaidSanitize.ts``.
"""

from __future__ import annotations

from app.services.md_fence_scan import map_closed_fences
from app.services.text_match import parens_balanced

# Marks of the shapes drawn inside ``[...]``: cylinder, parallelograms, trapezoids.
_SHAPE_EDGES: tuple[tuple[str, str], ...] = (
    ("(", ")"),
    ("/", "/"),
    ("\\", "\\"),
    ("/", "\\"),
    ("\\", "/"),
)


# ``["…"]`` is quoted already; ``[[…]]`` is a subroutine box.
_BRACKETS: dict[str, tuple[str, str]] = {'"': ('["', '"]'), "[": ("[[", "]]")}


def _is_quoted(text: str) -> bool:
    return len(text) >= 2 and text[0] == '"' and text[-1] == '"'


def _shape_edge(body: str) -> tuple[str, str]:
    for open_mark, close_mark in _SHAPE_EDGES:
        if len(body) < 2 or not (body.startswith(open_mark) and body.endswith(close_mark)):
            continue
        # ``[(a) and (b)]`` is a box whose label opens and closes with brackets.
        if open_mark == "(" and not parens_balanced(body[1:-1]):
            continue
        return open_mark, close_mark
    return "", ""


def quote_mermaid_label(body: str) -> str:
    """The text between a node's brackets, with any parenthesised label quoted."""
    open_mark, close_mark = _shape_edge(body)
    label = body[len(open_mark) : len(body) - len(close_mark)]
    if ("(" not in label and ")" not in label) or _is_quoted(label):
        return body
    quoted = label.replace('"', "'")
    return f'{open_mark}"{quoted}"{close_mark}'


def sanitize_mermaid_node_labels(text: str) -> str:
    """Quote the parenthesised labels of ``[...]`` nodes, keeping their shapes.

    Leaves already-quoted labels and stadium ``start([Start])`` (inner text
    has no parens) unchanged; ``[[...]]`` is a subroutine box.
    """
    if "(" not in text and ")" not in text:
        return text
    pieces: list[str] = []
    index = 0
    while index < len(text):
        bracket = text.find("[", index)
        if bracket < 0:
            pieces.append(text[index:])
            break
        pieces.append(text[index:bracket])
        opener, closer = _BRACKETS.get(text[bracket + 1 : bracket + 2], ("[", "]"))
        close = text.find(closer, bracket + len(opener))
        if close < 0:
            pieces.append(text[bracket:])
            break
        if opener == '["':
            pieces.append(text[bracket : close + 2])
        else:
            body = text[bracket + len(opener) : close]
            pieces.append(f"{opener}{quote_mermaid_label(body)}{closer}")
        index = close + len(closer)
    return "".join(pieces)


def _wrap_mermaid_body(body: str) -> str:
    sanitized = sanitize_mermaid_node_labels(body)
    if not sanitized.endswith("\n"):
        sanitized += "\n"
    return f"```mermaid\n{sanitized}```\n"


def sanitize_mermaid_fences(text: str) -> str:
    """Rewrite closed ```mermaid fences so parenthetical labels are quoted."""
    if "```mermaid" not in text.lower():
        return text
    return map_closed_fences(text, "mermaid", _wrap_mermaid_body)
