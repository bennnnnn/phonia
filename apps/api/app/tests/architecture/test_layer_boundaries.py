"""Static dependency-boundary checks for the API layers."""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
LOWER_LAYER_DIRS = (APP_ROOT / "gateways", APP_ROOT / "repositories")


def _service_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "app.services" or module.startswith("app.services."):
                violations.append((node.lineno, module))
            elif module == "app" and any(alias.name == "services" for alias in node.names):
                violations.append((node.lineno, "app.services"))
            elif node.level >= 2 and (
                module == "services"
                or module.startswith("services.")
                or (not module and any(alias.name == "services" for alias in node.names))
            ):
                violations.append((node.lineno, f"{'.' * node.level}{module or 'services'}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services" or alias.name.startswith("app.services."):
                    violations.append((node.lineno, alias.name))
    return violations


def test_gateways_and_repositories_do_not_import_services() -> None:
    violations: list[str] = []
    for directory in LOWER_LAYER_DIRS:
        for path in sorted(directory.rglob("*.py")):
            for line, module in _service_imports(path):
                relative = path.relative_to(APP_ROOT)
                violations.append(f"{relative}:{line} imports {module}")

    assert not violations, (
        "Gateways and repositories are lower-level dependencies and must not "
        "import app.services:\n" + "\n".join(violations)
    )
