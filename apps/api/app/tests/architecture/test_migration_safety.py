"""Migrations stay deployable: one head, and no drop in the release that stops reading it.

The release command migrates before any Machine is replaced, and blue-green
keeps the old release serving until the new one is healthy; a rollback
redeploys an older image on the newer schema. 0099 and 0106 dropped columns in
the same release as the code that stopped reading them, so the old Machines
and worker failed during the deploy and "redeploy the known-good image" was no
longer possible. The rule (docs/ROLLBACK.md, "Schema changes: expand, then
contract"): add first; drop, rename or retype only in a later release, once no
deployed code reads the old shape, and say so with an ``# expand-contract:``
comment in ``upgrade()``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from .boundary_support import APP_ROOT

API_ROOT = APP_ROOT.parent
VERSIONS = API_ROOT / "alembic" / "versions"
# Written before the rule; never rewritten. A new migration is numbered above.
LAST_GRANDFATHERED = 111
MARKER = "# expand-contract:"
_CONTRACTING = re.compile(
    r"\b(drop_column|drop_table|rename_table)\b"
    r"|new_column_name\s*="
    r"|\bDROP\s+(COLUMN|TABLE)\b"
    r"|\bRENAME\s+(COLUMN|TO)\b",
    re.IGNORECASE,
)


def _upgrade_source(source: str) -> str:
    """Text of ``upgrade()`` (comments included); the downgrade may drop freely."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "upgrade":
            lines = source.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


def contracts_without_marker(source: str) -> bool:
    upgrade = _upgrade_source(source)
    return bool(_CONTRACTING.search(upgrade)) and MARKER not in upgrade


def _number(path: Path) -> int | None:
    found = re.match(r"(\d{4})_", path.name)
    return int(found.group(1)) if found else None


@pytest.mark.parametrize(
    "upgrade, flagged",
    [
        ('    op.add_column("users", sa.Column("x", sa.Text()))', False),
        ('    op.drop_column("users", "legacy")', True),
        ('    op.drop_table("job_matches")', True),
        ('    op.execute("ALTER TABLE users DROP COLUMN legacy")', True),
        ('    op.alter_column("users", "a", new_column_name="b")', True),
        ('    op.drop_index("ix_old", table_name="users")', False),
        (
            "    # expand-contract: 0118 stopped reading users.legacy (two releases ago)\n"
            '    op.drop_column("users", "legacy")',
            False,
        ),
    ],
)
def test_the_guard_reads_upgrade_only(upgrade: str, flagged: bool) -> None:
    source = (
        "def upgrade() -> None:\n"
        f"{upgrade}\n\n\n"
        "def downgrade() -> None:\n"
        '    op.drop_column("users", "x")\n'
    )
    assert contracts_without_marker(source) is flagged


def test_new_migrations_contract_only_with_a_marker() -> None:
    offenders = [
        path.name
        for path in sorted(VERSIONS.glob("*.py"))
        if (_number(path) or 0) > LAST_GRANDFATHERED
        and contracts_without_marker(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} drop, rename or retype in upgrade(). Ship the code that stops "
        "reading the old column/table first; drop it in a later release with a "
        f"'{MARKER} <which release stopped reading it>' comment in upgrade() "
        "(docs/ROLLBACK.md)."
    )


def test_migrations_have_one_head() -> None:
    config = Config()
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"alembic has {len(heads)} heads {heads}; add a merge revision"
