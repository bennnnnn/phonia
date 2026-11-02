import pytest

from app.modules.chat.mermaid_sanitize import (
    sanitize_mermaid_fences,
    sanitize_mermaid_node_labels,
)
from app.modules.chat.prompt_constants import MERMAID_FORMAT_HINT

GRIND = "D --> E[Grind Beans (Medium Grind)]"
GRIND_QUOTED = 'D --> E["Grind Beans (Medium Grind)"]'


def test_quotes_parenthetical_rectangle_label() -> None:
    assert sanitize_mermaid_node_labels(GRIND) == GRIND_QUOTED


def test_already_quoted_labels_unchanged() -> None:
    assert sanitize_mermaid_node_labels(GRIND_QUOTED) == GRIND_QUOTED


def test_stadium_start_unchanged() -> None:
    line = "start([Start]) --> step[Do the work]"
    assert sanitize_mermaid_node_labels(line) == line


def test_closed_fence_body_is_quoted() -> None:
    raw = "```mermaid\nflowchart TD\n  D --> E[Grind Beans (Medium Grind)]\n```\n"
    out = sanitize_mermaid_fences(raw)
    assert 'E["Grind Beans (Medium Grind)"]' in out
    assert MERMAID_FORMAT_HINT not in out
    assert "```mermaid" in out


# Same cases as the phone twin (lib/__tests__/mermaidSanitize.test.ts).
@pytest.mark.parametrize(
    ("line", "want"),
    [
        # A cylinder stays a cylinder, not a box reading "(Database)".
        ("API --> DB[(Database)]", "API --> DB[(Database)]"),
        ("Cache[(Cache<br>Redis/Memcached)]", "Cache[(Cache<br>Redis/Memcached)]"),
        ("DB[(Primary (rw))]", 'DB[("Primary (rw)")]'),
        # Brackets that open and close the label are not a cylinder.
        ("A[(a) and (b)]", 'A["(a) and (b)"]'),
        ("S[[Validate (strict)]]", 'S[["Validate (strict)"]]'),
        ("S[[Validate]] --> T", "S[[Validate]] --> T"),
        ("I[/Read input (CSV)/]", 'I[/"Read input (CSV)"/]'),
        ("T[\\Manual step (optional)/]", 'T[\\"Manual step (optional)"/]'),
        ("start([Begin (now)])", 'start(["Begin (now)"])'),
    ],
)
def test_sanitize_mermaid_node_labels_keeps_shapes(line: str, want: str) -> None:
    assert sanitize_mermaid_node_labels(line) == want


def test_sanitize_mermaid_fences_keeps_database_cylinders() -> None:
    raw = (
        "```mermaid\nflowchart LR\n"
        "    API1 --> Cache[(Cache<br>Redis/Memcached)]\n"
        "    Cache --> DB[(Database<br>Primary)]\n"
        "    DB --> Replica[(Read Replicas)]\n```\n"
    )
    out = sanitize_mermaid_fences(raw)
    assert "Cache[(Cache<br>Redis/Memcached)]" in out
    assert "DB[(Database<br>Primary)]" in out
    assert "Replica[(Read Replicas)]" in out
