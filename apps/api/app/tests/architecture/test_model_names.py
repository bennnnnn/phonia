"""Product code names no model; the catalog and the routing lanes do (code-health audit ARCH-06).

Two maths jobs asked ``"gpt-6-luna"`` by name, a model the user picks, so retiring it
would have broken word problems at runtime, and the lane test never saw them. Chat's
settings reader kept its own list of five model ids ("switch to GLM" found nothing) and
the settings card its own labels, unlike Settings → Models. Now a job asks its lane
(``ROUTING.word_problems``), and the reader and the card read the catalog.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.models import model_catalog

from .boundary_support import APP_ROOT

# Product code: the domains and their shared leaves. The catalog, the lanes and the
# gateways (each provider's boundary) are where model names belong.
_PRODUCT = ("modules", "services", "background")


def _model_names() -> set[str]:
    """Every id the user can pick, and every provider model the catalog maps to."""
    names = {model.id for model in model_catalog.selectable_models()}
    for model in model_catalog.CATALOG:
        names.add(model.model)
        names.add(model.model.rsplit("/", 1)[-1])
    return names


def _sources() -> list[Path]:
    return [
        path
        for folder in _PRODUCT
        for path in sorted((APP_ROOT / folder).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def test_no_job_asks_a_model_by_a_written_name() -> None:
    written = [
        f"{path.relative_to(APP_ROOT)}:{node.lineno} model_alias={node.value.value!r}"
        for path in _sources()
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.keyword)
        and node.arg == "model_alias"
        and isinstance(node.value, ast.Constant)
    ]
    assert written == [], "ask the job's lane (models/routing_lanes.py)"


def test_no_product_code_names_a_model() -> None:
    names = _model_names()
    named = [
        f"{path.relative_to(APP_ROOT)}:{node.lineno} {node.value!r}"
        for path in _sources()
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names
    ]
    assert named == [], "a lane, the user's pick or the catalog names a model, not product code"
