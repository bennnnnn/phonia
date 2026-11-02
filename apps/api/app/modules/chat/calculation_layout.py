"""One logical reasoning state per math row, for every subject's reply before it is saved.

The phone's twin is apps/mobile/lib/markdown/calculationLayout.ts; the shared corpus
docs/fixtures/presentation_cases.json holds both to one output. A row stays together when it
is one formula, one substitution, or one simple evaluation. A chain of transformations, or
two independent equations, becomes separate rows, unless its sentence goes on after it.
"""

from __future__ import annotations

import re

from app.modules.chat.calculation_layout_tail import (
    continues_sentence,
    converts_units,
    finish_inline,
    keep_hard_break,
    reads_as_prose,
)
from app.modules.chat.inline_code import code_span_opens_within, escaped_at, is_bare_number
from app.modules.chat.markdown_regions import (
    display_math_lines,
    leave_prose_line,
    rewrite_fenced,
)
from app.services.md_fence_scan import read_fence_marker

_MATH_FENCE_LANGS = {"math", "latex", "tex", "equation"}
_TEXT_COMMANDS = {"text", "mathrm", "mathbf", "textrm", "operatorname", "textbf", "mbox"}
_NUMERIC_COMMANDS = {"times", "cdot", "div", "left", "right", "pm", "mp", "cdotp", "quad", "qquad"}
# A gap that names a new relationship is one step, not another value of the first side.
_CHAIN_STOP_COMMANDS = {
    "rightarrow",
    "leftarrow",
    "Rightarrow",
    "Leftarrow",
    "to",
    "implies",
    "iff",
    "Leftrightarrow",
    "mapsto",
    "quad",
    "qquad",
}
_CHAIN_STOP_WORDS = {"or", "and"}
_TRAILING_PUNCT = set(".,;:!?")


def split_math_expression(expr: str) -> list[str] | None:
    """Return separate reasoning rows, or None when the expression stays one row."""
    body = expr.strip()
    if not body or r"\begin{" in body or "&" in body:
        return None
    pieces = _independent_pieces(body)
    if pieces is not None:
        rows: list[str] = []
        for piece in pieces:
            nested = _equals_chain(piece)
            rows.extend(nested if nested else [piece.strip()])
        return rows if len(rows) >= 2 else None
    return _equals_chain(body)


def layout_calculations(text: str) -> str:
    """Split chained calculations in assistant prose and math fences."""
    if not text:
        return text
    return rewrite_fenced(text, _layout_prose, _rewrite_math_fence)


def _command_end(text: str, index: int) -> tuple[str, int]:
    cursor = index + 1
    if cursor >= len(text):
        return "", cursor
    if text[cursor].isalpha():
        start = cursor
        cursor += 1
        while cursor < len(text) and text[cursor].isalpha():
            cursor += 1
        return text[start:cursor], cursor
    return text[cursor], cursor + 1


def _tokenize(expr: str) -> list[tuple[str, int, int, bool]]:
    """Yield ``(kind, start, end, top_level)`` for relations and row breaks."""
    out: list[tuple[str, int, int, bool]] = []
    brace = paren = bracket = 0
    index = 0
    length = len(expr)
    while index < length:
        top = brace == 0 and paren == 0 and bracket == 0
        char = expr[index]
        if char == "\\":
            name, end = _command_end(expr, index)
            kind = "command"
            if name == "approx":
                kind = "approx"
            elif name in {"quad", "qquad"}:
                kind = "break"
            out.append((kind, index, end, top))
            index = end
            continue
        if char == "{":
            brace += 1
        elif char == "}":
            brace = max(0, brace - 1)
        elif char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "=" and top:
            out.append(("equals", index, index + 1, True))
        elif char == "," and top and not _thousands_separator(expr, index):
            end = _break_end(expr, index)
            out.append(("break", index, end, True))
            index = end
            continue
        index += 1
    return out


# ``1,500``: a digit, the comma, then exactly three digits (ASCII, as on the phone). ``10, 2x``
# is two equations: read as one number, ``x + y = 10, 2x - y = 5`` got a row ``x + y = 5``.
_GROUPED_DIGITS = re.compile(r"(?<=[0-9]),[0-9]{3}(?![0-9])")


def _thousands_separator(expr: str, index: int) -> bool:
    return _GROUPED_DIGITS.match(expr, index) is not None


def _break_end(expr: str, index: int) -> int:
    cursor = index + 1
    while cursor < len(expr) and expr[cursor] == " ":
        cursor += 1
    if expr.startswith("\\quad", cursor) or expr.startswith("\\qquad", cursor):
        return _command_end(expr, cursor)[1]
    return index + 1


def _has_top_equals(expr: str) -> bool:
    return any(kind == "equals" and top for kind, _start, _end, top in _tokenize(expr))


def _independent_pieces(expr: str) -> list[str] | None:
    breaks = [tok for tok in _tokenize(expr) if tok[0] == "break" and tok[3]]
    if not breaks:
        return None
    pieces: list[str] = []
    start = 0
    for _kind, break_start, break_end, _top in breaks:
        piece = expr[start:break_start].strip()
        if piece:
            pieces.append(piece)
        start = break_end
    tail = expr[start:].strip()
    if tail:
        pieces.append(tail)
    if len(pieces) < 2 or not all(_has_top_equals(piece) for piece in pieces):
        return None
    return pieces


def _equals_chain(expr: str) -> list[str] | None:
    ops = [tok for tok in _tokenize(expr) if tok[3] and tok[0] in {"equals", "approx"}]
    if len(ops) < 2:
        return None
    segments: list[str] = []
    start = 0
    for _kind, op_start, op_end, _top in ops:
        segments.append(expr[start:op_start])
        start = op_end
    segments.append(expr[start:])
    if any(not part.strip() for part in segments):
        return None
    if any(_segment_blocks_chain(part) for part in segments[1:-1]):
        return None
    if all(_is_simple_numeric(part) for part in segments) or converts_units(segments):
        return None
    lhs = segments[0].strip()
    rows: list[str] = []
    for index, rhs in enumerate(segments[1:]):
        op = r"\approx" if ops[index][0] == "approx" else "="
        rows.append(f"{lhs} {op} {rhs.strip()}")
    return rows


def _segment_blocks_chain(segment: str) -> bool:
    """True when this gap introduces another equation instead of the next value."""
    index = 0
    length = len(segment)
    while index < length:
        if segment[index] == "\\":
            name, end = _command_end(segment, index)
            if name in _CHAIN_STOP_COMMANDS:
                return True
            index = end
            continue
        if segment[index].isalpha():
            start = index
            index += 1
            while index < length and segment[index].isalpha():
                index += 1
            if segment[start:index].lower() in _CHAIN_STOP_WORDS:
                return True
            continue
        index += 1
    return False


def _is_simple_numeric(segment: str) -> bool:
    index = 0
    length = len(segment)
    while index < length:
        if segment[index] == "\\":
            name, end = _command_end(segment, index)
            if name in _TEXT_COMMANDS:
                # A unit or label is a different quantity, not a factorial expansion.
                return False
            if name in _NUMERIC_COMMANDS or not name.isalpha():
                index = end
                continue
            return False
        if segment[index].isalpha():
            return False
        index += 1
    return True


def _join_rows(rows: list[str], delim: str, punct: str = "") -> str:
    lines = [f"{delim}{row}{delim}" for row in rows]
    if punct:
        lines[-1] = f"{lines[-1]}{punct}"
    if len(lines) == 1:
        return lines[0]
    return "\n".join(
        f"{line}  " if index < len(lines) - 1 else line for index, line in enumerate(lines)
    )


def _peel_punct(text: str) -> tuple[str, str]:
    end = size = len(text)  # back by index: a copy per mark was quadratic in a run of marks
    while end and (text[end - 1] in _TRAILING_PUNCT or (end < size and text[end - 1].isspace())):
        end -= 1
    return text[:end], "".join(char for char in text[end:] if char in _TRAILING_PUNCT)


def _sole_math(stripped: str) -> tuple[str, str, str] | None:
    core, punct = _peel_punct(stripped)
    if core.startswith("$$") and core.endswith("$$") and len(core) > 4:
        inner = core[2:-2].strip()
        if inner and "$$" not in inner:
            return "$$", inner, punct
    if (
        len(core) > 2
        and core.startswith("$")
        and core.endswith("$")
        and not core.startswith("$$")
        and "$" not in core[1:-1]
    ):
        inner = core[1:-1].strip()
        if inner:
            return "$", inner, punct
    return None


def _plain_chain(body: str) -> str | None:
    if reads_as_prose(body):
        return None
    core, punct = _peel_punct(body.strip())
    rows = split_math_expression(core)
    if not rows:
        return None
    return _join_rows(rows, "$", punct)


def _read_code_end(text: str, index: int) -> int | None:
    length = 0
    while index + length < len(text) and text[index + length] == "`":
        length += 1
    if length == 0:
        return None
    close = text.find("`" * length, index + length)
    if close < 0 or close == index + length or "\n" in text[index + length : close]:
        return None
    return close + length


def _read_math_span(text: str, index: int) -> tuple[str, str, int] | None:
    if text.startswith("$$", index):
        close = text.find("$$", index + 2)
        if close < 0 or close == index + 2 or "\n" in text[index + 2 : close]:
            return None
        if code_span_opens_within(text, index + 2, close):
            return None
        return "$$", text[index + 2 : close].strip(), close + 2
    if text[index] != "$":
        return None
    close = text.find("$", index + 1)
    if close < 0 or "\n" in text[index + 1 : close]:
        return None
    if close + 1 < len(text) and text[close + 1] == "$":
        return None
    # A pair never reaches across an inline code span, or splitting the
    # "chain" at its = signs rewrites the code between the dollars.
    if code_span_opens_within(text, index + 1, close):
        return None
    inner = text[index + 1 : close]
    if not inner.strip():
        return None
    if (
        inner[0].isdigit()
        and not any(char in inner for char in "\\=^_")
        and not is_bare_number(inner, text[close + 1 : close + 2])
    ):
        return None
    return "$", inner.strip(), close + 1


def _layout_inline(body: str) -> str:
    parts: list[str] = []
    buf: list[str] = []
    changed = False
    index = 0
    length = len(body)
    while index < length:
        if body[index] == "\\":
            end = _command_end(body, index)[1]
            buf.append(body[index:end])
            index = end
            continue
        if body[index] == "`":
            code_end = _read_code_end(body, index)
            if code_end is None:
                buf.append(body[index])
                index += 1
            else:
                buf.append(body[index:code_end])
                index = code_end
            continue
        span = _read_math_span(body, index)
        if span is None:
            buf.append(body[index])
            index += 1
            continue
        delim, inner, end = span
        rows = split_math_expression(inner)
        if not rows or continues_sentence(body[end:]):
            buf.append(body[index:end])
            index = end
            continue
        changed = True
        lead = "".join(buf)
        buf = []
        if lead.strip():
            parts.append(lead.rstrip())
        cursor = end
        while cursor < length and body[cursor] in _TRAILING_PUNCT:
            cursor += 1
        parts.append(_join_rows(rows, delim, body[end:cursor]))
        index = cursor
    if not changed:
        return body
    return finish_inline(parts, "".join(buf))


def _layout_body(body: str) -> str:
    stripped = body.strip()
    sole = _sole_math(stripped) if stripped else None
    if sole is not None:
        delim, inner, punct = sole
        rows = split_math_expression(inner)
        if not rows:
            return body
        joined = keep_hard_break(body, _join_rows(rows, delim, punct))
        indent = body[: len(body) - len(body.lstrip(" "))]
        if not indent:
            return joined
        return "\n".join(f"{indent}{line}" for line in joined.split("\n"))
    # A closed \[...\] on one line is one display formula, drawn as a maths block.
    if "$" not in body and "`" not in body and "\\[" not in body:
        plain = _plain_chain(body)
        if plain is not None:
            indent = body[: len(body) - len(body.lstrip(" "))]
            if indent and plain != body:
                return "\n".join(f"{indent}{line}" for line in plain.split("\n"))
            return plain
    return _layout_inline(body)


def _list_prefix(line: str) -> tuple[str, str]:
    index = 0
    while index < len(line) and line[index] == " ":
        index += 1
    rest = line[index:]
    for marker in ("- ", "* ", "+ "):
        if rest.startswith(marker):
            return line[: index + 2], rest[2:]
    digits = 0
    while digits < len(rest) and rest[digits].isdigit():
        digits += 1
    if 0 < digits <= 3 and rest[digits : digits + 2] == ". ":
        return line[: index + digits + 2], rest[digits + 2 :]
    return "", line


def _layout_line(line: str) -> str:
    if leave_prose_line(line):
        return line
    stripped = line.lstrip(" ")
    if stripped.startswith("|") or stripped.startswith("#"):
        return line
    prefix, body = _list_prefix(line)
    laid = _layout_body(body)
    if laid == body:
        return line
    if not prefix:
        return laid
    rows = laid.split("\n")
    pad = " " * len(prefix)
    return "\n".join(prefix + row if index == 0 else pad + row for index, row in enumerate(rows))


def _interior_line_blocks_fold(line: str) -> bool:
    """A new block inside \\(...\\) is not one inline formula."""
    if leave_prose_line(line):
        return True
    stripped = line.lstrip(" ")
    if not stripped:
        return False
    if stripped.startswith(("|", "#", "- ", "* ", "+ ")) or read_fence_marker(stripped):
        return True
    digits = 0
    while digits < len(stripped) and stripped[digits].isdigit():
        digits += 1
    return 0 < digits <= 3 and stripped[digits : digits + 2] == ". "


def _span_crosses_preserved_line(text: str, start: int, close: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    lines = text[line_start:close].split("\n")
    if lines and leave_prose_line(lines[0]):
        return True
    return any(_interior_line_blocks_fold(line) for line in lines[1:])


def _find_paren_closer(text: str, start: int) -> int | None:
    index = start
    length = len(text)
    while index < length:
        if text[index] == "`":
            code_end = _read_code_end(text, index)
            if code_end is not None:
                index = code_end
                continue
        if text.startswith(r"\)", index) and not escaped_at(text, index):
            return index
        index += 1
    return None


def _fold_closed_paren_math(text: str) -> str:
    """Turn a finished \\(...\\) into ``$...$`` so a chain can split.

    An opener with no closer stays literal. Streaming hides that tail until
    the closer arrives, and this pass must not invent a ``$`` there.
    """
    if r"\(" not in text:
        return text
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "`":
            code_end = _read_code_end(text, index)
            if code_end is not None:
                out.append(text[index:code_end])
                index = code_end
                continue
        if text.startswith(r"\(", index) and not escaped_at(text, index):
            close = _find_paren_closer(text, index + 2)
            if close is None:
                out.append(text[index:])
                break
            if _span_crosses_preserved_line(text, index, close):
                out.append(text[index : close + 2])
                index = close + 2
                continue
            raw = text[index + 2 : close]
            if "\n" in raw or "\r" in raw:
                raw = " ".join(part.strip() for part in raw.splitlines())
            if not raw.strip():
                out.append(text[index : close + 2])
            else:
                out.append(f"${raw}$")
            index = close + 2
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def _layout_prose(prose: str) -> str:
    lines = _fold_closed_paren_math(prose).split("\n")
    pairs = zip(lines, display_math_lines(lines), strict=True)
    return "\n".join(line if kept else _layout_line(line) for line, kept in pairs)


def _unwrap_math_line(line: str) -> str:
    sole = _sole_math(line.strip())
    if sole is None:
        return line.strip()
    return sole[1]


def _rewrite_math_fence(opener: str, body: str, _closer: str) -> str | None:
    marker = read_fence_marker(opener)
    lang = marker.lang if marker is not None else ""
    if lang not in _MATH_FENCE_LANGS:
        return None
    physical = [line for line in body.split("\n") if line.strip()]
    if not physical:
        return None
    rows: list[str] = []
    changed = False
    for line in physical:
        inner = _unwrap_math_line(line)
        split = split_math_expression(inner)
        if split:
            changed = True
            rows.extend(split)
        else:
            rows.append(inner)
    if not changed:
        return None
    return _join_rows(rows, "$")
