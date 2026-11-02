"""A search result's table as the model reads it: one line per row, each with its own date.

Search pages arrive as markdown, and a table loses its merged cells on the way. Wikipedia's
iPhone table came as

    | Release date | Model | System-on-a-chip |
    | September 18, 2026 | iPhone 18 Pro | Apple A20 Pro |
    | iPhone 18 Pro Max |
    | October 23, 2026 | iPhone Duo |

where the Pro Max shares the row above's date and chip. The prompt flattened the snippet
onto one line, "| iPhone 18 Pro Max | | October 23, 2026 | iPhone Duo |", and a reply gave
the Pro Max the Duo's date (2026-10-23); asked about the Pro Max alone, replies said it had
not come out or that the results gave it no date. A table with a header and a date column
now reaches the model one row per line, each value named by its column. A row whose date
cell is missing lost it to a merged cell, and so did any other cell it lacks: it carries
the row above's. A row with its own date carries nothing ("| 2020 | Cancelled |" is one
cell across two columns, not two merged ones). A row the snippet cut off is left out. Any
other table keeps its rows as written, each on its own line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.calendar_dates import MONTH_NAME, read_dates

_SEPARATOR_CELL = re.compile(r":?-{2,}:?")
# A cell that is only a year ("2025") or a month and a year ("Sept 2026").
_YEAR_CELL = re.compile(rf"(?:{MONTH_NAME}\.?,?\s+)?(?:19|20)\d\d", re.IGNORECASE)


@dataclass(frozen=True)
class _Row:
    cells: list[str]
    # Ends with "|": the snippet did not cut the row off.
    closed: bool


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _row(line: str) -> _Row:
    body = line.strip()[1:]
    closed = body.endswith("|")
    if closed:
        body = body[:-1]
    return _Row([cell.strip() for cell in body.split("|")], closed)


def _dated(cell: str) -> bool:
    return _YEAR_CELL.fullmatch(cell) is not None or bool(read_dates(cell))


def _is_separator(row: _Row) -> bool:
    return all(not cell or _SEPARATOR_CELL.fullmatch(cell) for cell in row.cells)


def _is_header(row: _Row) -> bool:
    """Column names: two or more, none blank, none a date or a number."""
    cells = row.cells
    return len(cells) >= 2 and all(
        cell and not _dated(cell) and not cell.replace(",", "").replace(".", "").isdigit()
        for cell in cells
    )


def _date_column(width: int, rows: list[_Row]) -> int | None:
    """The first column whose filled cells, in rows with every cell, are mostly dates."""
    full = [row.cells for row in rows if len(row.cells) == width]
    for column in range(width):
        filled = [cells[column] for cells in full if cells[column]]
        if filled and 2 * sum(_dated(cell) for cell in filled) > len(filled):
            return column
    return None


def _placed(cells: list[str], width: int, date_column: int) -> dict[int, str] | None:
    """The column each cell of a row fills; None when that can't be told.

    A row with a date puts it in the date column, the cells before it in the columns just
    before and the cells after it in the columns just after. A row without one lost its
    date to a merged cell; its cells fill the other columns from the left.
    """
    if len(cells) == width:
        return dict(enumerate(cells))
    dated = [index for index, cell in enumerate(cells) if _dated(cell)]
    if len(dated) > 1 or len(cells) > width:
        return None
    if dated:
        at = dated[0]
        before, after = cells[:at], cells[at + 1 :]
        if len(before) > date_column or len(after) > width - date_column - 1:
            return None
        placed = {date_column - len(before) + index: cell for index, cell in enumerate(before)}
        placed[date_column] = cells[at]
        placed.update({date_column + 1 + index: cell for index, cell in enumerate(after)})
        return placed
    others = [column for column in range(width) if column != date_column]
    return dict(zip(others, cells, strict=False))


def _records(rows: list[_Row]) -> list[str] | None:
    """Each data row as ``Column: value; …``, or None for a table this can't read."""
    header, data = rows[0], rows[1:]
    if not data or not _is_header(header):
        return None
    width = len(header.cells)
    date_column = _date_column(width, data)
    if date_column is None:
        return None
    records: list[str] = []
    above: dict[int, str] | None = None
    for row in data:
        placed = _placed(row.cells, width, date_column)
        if placed is None:
            return None
        if date_column not in placed:
            if above is None or not above.get(date_column):
                return None
            # The date went with the merged cells; any other cell missing went with it.
            placed = above | placed
        above = placed
        records.append(
            "; ".join(
                f"{header.cells[column]}: {value}"
                for column, value in sorted(placed.items())
                if value
            )
        )
    return records


def _table(lines: list[str], *, at_end: bool) -> list[str]:
    rows = [row for row in map(_row, lines) if not _is_separator(row)]
    # The snippet's length limit cut the last row off mid-cell ("| iPhone 18 ").
    if at_end and len(rows) > 1 and not rows[-1].closed and rows[-2].closed:
        rows = rows[:-1]
    records = _records(rows) if rows else None
    return records if records is not None else [line.strip() for line in lines]


def snippet_lines(snippet: str) -> list[tuple[str, bool]]:
    """The snippet's lines, each with whether it is a table row (rewritten as above)."""
    lines = snippet.split("\n")
    out: list[tuple[str, bool]] = []
    index = 0
    while index < len(lines):
        if not _is_table_line(lines[index]):
            out.append((lines[index], False))
            index += 1
            continue
        end = index
        while end < len(lines) and _is_table_line(lines[end]):
            end += 1
        at_end = not "".join(lines[end:]).strip()
        out.extend((row, True) for row in _table(lines[index:end], at_end=at_end))
        index = end
    return out


def tables_as_rows(snippet: str) -> str:
    """The snippet with each table rewritten as above; its other lines as written."""
    return "\n".join(line for line, _is_row in snippet_lines(snippet))


def flowed_snippet(snippet: str, *, indent: str) -> str:
    """The snippet on one line, as the search block shows a hit, but a table row on its own.

    Prose lines join with spaces as before; each table row starts a new line after ``indent``.
    """
    chunks: list[str] = []
    prose: list[str] = []
    for line, is_row in snippet_lines(snippet):
        if not is_row:
            prose.append(line)
            continue
        if text := " ".join(prose).strip():
            chunks.append(text)
        prose = []
        chunks.append(line)
    if text := " ".join(prose).strip():
        chunks.append(text)
    return f"\n{indent}".join(chunks)
