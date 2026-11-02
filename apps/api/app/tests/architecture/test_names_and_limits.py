"""Names say what they are, and a limit has one definition (code-health audit CLAR-14).

``GoogleAuthError`` was the app's auth error for Apple, the tokens and dev login too, so
``core`` took it from a Google gateway. 1,109 imports reached another file's
``_private`` names, so an underscore no longer said "file-local". And limits were typed
twice with different values: custom instructions saved at 1,000 characters but cut at
2,000, a to-do saved at 1,000 but cut at 500, the filename width and the upload size
retyped as literals.
"""

from __future__ import annotations

import ast
from typing import cast

from pydantic import BaseModel
from sqlalchemy import String

from app.core.attachment_limits import MAX_ATTACHMENT_SIZE
from app.models.schemas.auth import CUSTOM_INSTRUCTIONS_MAX_CHARS, UserUpdate
from app.modules.attachments.models import ORIGINAL_FILENAME_MAX_CHARS, Attachment
from app.modules.attachments.schemas import AttachmentPresignIn
from app.modules.todos.schemas import TODO_TEXT_MAX_CHARS, TodoCreate, TodoUpdate
from app.services.prompt_safety import custom_instructions_block

from .boundary_support import APP_ROOT

# Imports of another file's ``_private`` names; lower it when a change removes some.
_PRIVATE_IMPORTS = 720


def _production() -> list[tuple[str, ast.Module]]:
    return [
        (str(path.relative_to(APP_ROOT)), ast.parse(path.read_text()))
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in path.relative_to(APP_ROOT).parts
    ]


def test_imports_of_private_names_only_go_down() -> None:
    count = sum(
        1
        for _name, tree in _production()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.")
        for alias in node.names
        if alias.name.startswith("_") and not alias.name.startswith("__")
    )
    assert count <= _PRIVATE_IMPORTS, "another file's _name: drop the underscore, it is shared"
    assert count == _PRIVATE_IMPORTS, f"fewer now: set _PRIVATE_IMPORTS = {count}"


def test_no_module_is_named_for_being_shared() -> None:
    """Physics kept two ``common.py`` files of unrelated helpers: patterns, value readers,
    gravity, result types, SI conversion. Each part now lives in a file named for it."""
    drawers = sorted(
        str(path.relative_to(APP_ROOT))
        for path in (APP_ROOT / "modules").rglob("*.py")
        if path.stem in {"common", "utils", "helpers", "misc"}
    )
    assert drawers == [], "name the file for what it holds"


def test_the_google_error_belongs_to_the_google_gateway() -> None:
    elsewhere = [
        name
        for name, tree in _production()
        if name != "gateways/google_auth.py"
        and any(
            isinstance(node, ast.Name) and node.id == "GoogleAuthError" for node in ast.walk(tree)
        )
    ]
    assert elsewhere == [], "raise or catch AuthenticationError (app/exceptions.py)"


def _bound(schema: type[BaseModel], field: str, kind: str) -> object:
    """A field's ``max_length`` or ``le``, wherever pydantic put it among the metadata."""
    return next(
        getattr(item, kind)
        for item in schema.model_fields[field].metadata
        if getattr(item, kind, None) is not None
    )


def test_each_limit_has_one_value() -> None:
    assert _bound(UserUpdate, "custom_instructions", "max_length") == CUSTOM_INSTRUCTIONS_MAX_CHARS
    block = custom_instructions_block("x" * (CUSTOM_INSTRUCTIONS_MAX_CHARS * 3))
    assert block is not None and "x" * (CUSTOM_INSTRUCTIONS_MAX_CHARS + 1) not in block
    for schema in (TodoCreate, TodoUpdate):
        assert _bound(schema, "content", "max_length") == TODO_TEXT_MAX_CHARS
    column = cast(String, Attachment.__table__.c.original_filename.type)
    assert column.length == ORIGINAL_FILENAME_MAX_CHARS
    assert _bound(AttachmentPresignIn, "filename", "max_length") == ORIGINAL_FILENAME_MAX_CHARS
    assert _bound(AttachmentPresignIn, "size_bytes", "le") == MAX_ATTACHMENT_SIZE
