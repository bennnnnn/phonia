"""Shared paths, legacy catalogs, and checks for module-boundary tests."""

from __future__ import annotations

import ast
import importlib.util
from collections import deque
from collections.abc import Iterable
from functools import cache
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parents[2]
MOBILE_ROOT = REPO_ROOT / "apps" / "mobile"

# Compatibility paths left behind by the module migrations. Each one was deleted
# once nothing imported it; ``test_legacy_paths_removed`` keeps them gone.
RETIRED_LEGACY_MODULES: tuple[str, ...] = (
    "app.background.attachment_indexing",
    "app.background.attachment_orphan_reaper",
    "app.background.compaction",
    "app.background.gmail_periodic_sync",
    "app.background.gmail_sync",
    "app.background.memory_consolidation",
    "app.background.memory_extraction",
    "app.background.suggestion_generation",
    "app.background.todo_sync",
    # A one-line re-export of ``services.topic.generate_chat_title``.
    "app.background.topic_generation",
    "app.models.memory_ops",
    # Held only PushToken after the Google integrations were removed: ``orm.push_tokens``.
    "app.models.orm.integrations",
    "app.models.orm.memory",
    "app.models.orm.schedule",
    "app.models.orm.suggestions",
    "app.models.schemas.attachments",
    "app.models.schemas.chemistry",
    # Split into ``classification`` and ``push``; its speech re-exports had no importer.
    "app.models.schemas.integrations",
    "app.models.schemas.math",
    "app.models.schemas.memory",
    "app.models.schemas.physics",
    "app.models.schemas.schedule",
    "app.modules.chat.prompt_constants.physics",
    # The chat stream's seam module: stages take ``turn_deps.ChatTurnDeps`` (ES-23).
    "app.modules.chat.stream",
    "app.modules.chemistry.legacy_alias",
    "app.modules.math.legacy_alias",
    # Split by job: ``equations``, ``equation_conditions``, ``root_latex``, ``systems``,
    # ``numeric``, ``expressions``, ``inequalities`` (ES-34).
    "app.modules.math.solve.algebra",
    "app.modules.math.sympy_executor",
    # Split by job: ``request_text``, ``expr_rewrite``, ``function_def``, ``direct_newton`` (ES-34).
    "app.modules.math.tools.helpers",
    "app.modules.notifications.legacy_alias",
    "app.modules.physics.legacy_alias",
    "app.modules.suggestions.api",
    "app.modules.web_search.legacy_alias",
    "app.repositories.attachment_chunks",
    "app.repositories.attachments",
    "app.repositories.calendar_connections",
    # Conversation's tables: conversation.history reads them for other modules (ARCH-08).
    "app.repositories.chats",
    "app.repositories.gmail_connections",
    "app.repositories.memories",
    "app.repositories.message_chunks",
    "app.repositories.messages",
    "app.repositories.memory_writes",
    "app.repositories.search",
    "app.repositories.suggested_reminders",
    "app.repositories.suggestions",
    "app.repositories.todo_email",
    "app.repositories.todo_schedules",
    "app.repositories.todos",
    "app.routers.analytics",
    "app.routers.attachments",
    "app.routers.auth",
    "app.routers.chat_stream",
    "app.routers.chats",
    "app.routers.gmail_integrations",
    "app.routers.home",
    "app.routers.images",
    "app.routers.integrations",
    "app.routers.link_preview",
    "app.routers.memories",
    "app.routers.search",
    "app.routers.speech",
    "app.routers.speech_realtime",
    "app.routers.suggestions",
    "app.routers.todos",
    "app.routers.users",
    "app.routers.webhooks",
    "app.routers.ws",
    "app.services.account_lifecycle",
    "app.services.attachments",
    "app.services.auth",
    "app.services.calendar",
    "app.services.calendar_nudges",
    # Single-owner root files moved to their owner (code-health audit ARCH-03).
    "app.services.context_window",
    "app.services.chat",
    "app.services.chats",
    "app.services.chemistry",
    "app.services.email.context",
    "app.services.email.fence",
    "app.services.email.sender_templates",
    "app.services.email.triage",
    "app.services.export_service",
    "app.services.google_integrations",
    "app.services.home",
    "app.services.images",
    "app.services.link_preview",
    "app.services.live_talk",
    "app.services.live_talk_tools",
    "app.services.math",
    "app.services.mcp.calendar_adapter",
    "app.services.mcp.image_gen_adapter",
    "app.services.mcp.image_search_adapter",
    "app.services.mcp.sympy_adapter",
    "app.services.mcp.web_search_adapter",
    "app.services.memory",
    "app.services.mermaid_sanitize",
    # A second import path for ``models.model_catalog`` (code-health audit ARCH-05).
    "app.services.model_catalog",
    "app.services.notifications",
    "app.services.office_text",
    "app.services.part_answers",
    "app.services.physics",
    "app.services.plan",
    "app.services.product_analytics",
    "app.services.prompt_inject",
    "app.services.profile",
    # Model routing is chat's (``modules/chat/model_routing``, code-health audit ARCH-02).
    "app.services.rate_problems",
    "app.services.recurring_pay",
    "app.services.reply_labels",
    "app.services.revenuecat_webhook",
    "app.services.routing",
    "app.services.routing_physics",
    "app.services.routing_signals",
    "app.services.search",
    "app.services.settings_intent",
    "app.services.settings_proposal",
    "app.services.speech",
    "app.services.subscription",
    "app.services.suggestion_generation",
    "app.services.sympy_executor",
    "app.services.thinking_effort",
    "app.services.topic",
    "app.services.todos",
    "app.services.tokens",
    "app.services.tool_loop",
    "app.services.transcript_validation",
    "app.services.web_search",
    "app.services.web_session",
    "app.services.working_check",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _production_python() -> list[Path]:
    return [
        path
        for path in APP_ROOT.rglob("*.py")
        if "tests" not in path.parts and "__pycache__" not in path.parts
    ]


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP_ROOT.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _load_time_imports(nodes: Iterable[ast.AST]) -> list[ast.Import | ast.ImportFrom]:
    """Imports that run when the module loads: not in a function or ``if TYPE_CHECKING``."""
    found: list[ast.Import | ast.ImportFrom] = []
    for node in nodes:
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.append(node)
        elif isinstance(node, ast.If) and _is_type_checking(node.test):
            found.extend(_load_time_imports(node.orelse))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        elif isinstance(node, ast.stmt | ast.excepthandler | ast.match_case):
            # A block's statements, a class body's too; an expression holds no import.
            found.extend(_load_time_imports(ast.iter_child_nodes(node)))
    return found


def _runtime_imports(nodes: Iterable[ast.AST]) -> list[ast.Import | ast.ImportFrom]:
    """Imports that can run: inside functions too, never under ``if TYPE_CHECKING``."""
    found: list[ast.Import | ast.ImportFrom] = []
    for node in nodes:
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.append(node)
        elif isinstance(node, ast.If) and _is_type_checking(node.test):
            found.extend(_runtime_imports(node.orelse))
        else:
            found.extend(_runtime_imports(ast.iter_child_nodes(node)))
    return found


_IMPORT_FUNCTIONS = frozenset({"import_module", "__import__"})


def _dynamic_import_calls(
    tree: ast.AST,
) -> list[tuple[ast.Call, ast.expr | None, ast.expr | None]]:
    """Calls that import a module by name, in line order, with their name and ``package``
    arguments: ``importlib.import_module`` under any import name (``import importlib as il``,
    ``from importlib import import_module as load``) and ``__import__``. An ``__import__``
    with a level is relative to its caller by that level: its name counts as computed."""
    modules = {"importlib", "builtins"}
    functions = {name: name for name in _IMPORT_FUNCTIONS}  # local name -> what it is
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name in modules)
        elif isinstance(node, ast.ImportFrom) and node.module in {"importlib", "builtins"}:
            functions.update(
                {a.asname or a.name: a.name for a in node.names if a.name in _IMPORT_FUNCTIONS}
            )
    calls: list[tuple[ast.Call, ast.expr | None, ast.expr | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            kind = functions.get(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            kind = (
                func.attr if func.value.id in modules and func.attr in _IMPORT_FUNCTIONS else None
            )
        else:
            kind = None
        if kind is None:
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        name = node.args[0] if node.args else keywords.get("name")
        if kind == "import_module":
            package = node.args[1] if len(node.args) > 1 else keywords.get("package")
        else:
            level = node.args[4] if len(node.args) > 4 else keywords.get("level")
            package = None
            if level is not None and not (isinstance(level, ast.Constant) and level.value == 0):
                name = None
        calls.append((node, name, package))
    return sorted(calls, key=lambda call: (call[0].lineno, call[0].col_offset))


def _written_name(name: ast.expr | None, package: ast.expr | None, own_package: str) -> str | None:
    """The absolute module a dynamic import names in writing, or None when it is computed.
    ``import_module(".x", package=__package__)`` is relative to the caller's package."""
    if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        return None
    if not name.value.startswith("."):
        return name.value
    if isinstance(package, ast.Constant) and isinstance(package.value, str):
        anchor = package.value
    elif isinstance(package, ast.Name) and package.id == "__package__" and own_package:
        anchor = own_package
    else:
        return None
    try:
        return importlib.util.resolve_name(name.value, anchor)
    except ImportError:
        return None


def _named_dynamic_imports(tree: ast.AST, own_package: str = "") -> set[str]:
    """The module names dynamic imports spell out whole (a string, relative to a written package)."""
    return {
        written
        for _, name, package in _dynamic_import_calls(tree)
        if (written := _written_name(name, package, own_package)) is not None
    }


def computed_import_keys(label: str, tree: ast.AST, own_package: str = "") -> set[str]:
    """``label: expression`` of each dynamic import in ``tree`` whose module name is computed;
    a second call with the same expression is ``#2``, so each one is listed."""
    keys: set[str] = set()
    seen: dict[str, int] = {}
    for _, written, package in _dynamic_import_calls(tree):
        if _written_name(written, package, own_package) is not None:
            continue
        key = f"{label}: {ast.unparse(written) if written is not None else '?'}"
        seen[key] = seen.get(key, 0) + 1
        keys.add(key if seen[key] == 1 else f"{key} #{seen[key]}")
    return keys


def computed_dynamic_imports() -> set[str]:
    """Each production dynamic import whose module name is computed (an f-string or a
    variable): the import graph cannot follow it, so each one is listed by hand."""
    found: set[str] = set()
    for path in _production_python():
        tree = ast.parse(path.read_text(), filename=str(path))
        name = _module_name(path)
        own_package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        found |= computed_import_keys(path.relative_to(APP_ROOT).as_posix(), tree, own_package)
    return found


@cache
def _module_imports(*, load_time: bool, runtime: bool = False) -> dict[str, set[str]]:
    """Production module -> every module name its imports name, made absolute.

    ``from pkg import name`` names ``pkg`` and ``pkg.name``; a package is its ``__init__``.
    With ``load_time`` only imports that run when the module loads count: deferring an
    import into a function is the accepted way to break a load-order cycle. With
    ``runtime`` every import that can run counts, in a function too, but not one under
    ``if TYPE_CHECKING`` (an annotation is no dependency).
    """
    imports: dict[str, set[str]] = {}
    for path in _production_python():
        name = _module_name(path)
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        tree = ast.parse(path.read_text(), filename=str(path))
        if load_time:
            nodes = _load_time_imports(tree.body)
        elif runtime:
            nodes = _runtime_imports(tree.body)
        else:
            nodes = [
                node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)
            ]
        targets: set[str] = set()
        if runtime:
            # ``importlib.import_module("app.x")`` with a written name is an import too.
            targets.update(_named_dynamic_imports(tree, package))
        for node in nodes:
            if isinstance(node, ast.Import):
                targets.update(alias.name for alias in node.names)
                continue
            base = node.module or ""
            if node.level:
                anchor = package.rsplit(".", node.level - 1)[0]
                base = f"{anchor}.{base}" if base else anchor
            targets.add(base)
            targets.update(f"{base}.{alias.name}" for alias in node.names)
        imports[name] = targets
    return imports


def _import_graph(imports: dict[str, set[str]]) -> dict[str, set[str]]:
    """Each production module -> the production modules it imports."""
    return {name: (targets & imports.keys()) - {name} for name, targets in imports.items()}


def _import_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (iterative Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component: list[str] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        cycles.append(sorted(component))
            elif child not in index:
                index[child] = low[child] = len(index)
                stack.append(child)
                on_stack.add(child)
                work.append((child, iter(sorted(graph[child]))))
            elif child in on_stack:
                low[node] = min(low[node], index[child])
    return cycles


# What talks to a database, a cache, the network or the web framework. An ``app.core``
# module that wraps one (``redis_lock``, ``jobs``) is caught by the import it makes.
INFRASTRUCTURE: tuple[str, ...] = (
    "fastapi",
    "httpx",
    "litellm",
    "redis",
    "sqlalchemy",
    "starlette",
    "app.core.db",
    "app.core.redis",
    "app.gateways",
    "app.models.orm",
    "app.repositories",
)


def _infrastructure(names: Iterable[str]) -> list[str]:
    """The ``INFRASTRUCTURE`` roots these module names fall under."""
    return [
        root
        for root in INFRASTRUCTURE
        if any(name == root or name.startswith(f"{root}.") for name in names)
    ]


def _infrastructure_reached(packages: tuple[str, ...]) -> list[str]:
    """Each infrastructure import the packages reach, with the chain of modules to it.

    Every import counts, deferred and ``TYPE_CHECKING`` ones too: calling the function
    that holds a deferred import loads it.
    """
    imports = _module_imports(load_time=False)
    graph = _import_graph(imports)
    via: dict[str, str | None] = {
        name: None
        for name in sorted(graph)
        if any(name == package or name.startswith(f"{package}.") for package in packages)
    }
    queue = deque(via)
    while queue:
        name = queue.popleft()
        for child in sorted(graph[name]):
            if child not in via and not _infrastructure([child]):
                via[child] = name
                queue.append(child)
    violations: list[str] = []
    for name in via:
        reached = _infrastructure(imports[name])
        if not reached:
            continue
        chain = [name]
        while (step := via[chain[-1]]) is not None:
            chain.append(step)
        violations.append(f"{' -> '.join(reversed(chain))} imports {', '.join(reached)}")
    return violations


_PUBLIC_MODULE_TAILS = frozenset({"api", "schemas", "service", "crud"})


def _package_public_names(module_name: str) -> frozenset[str]:
    """Public tails plus names the package initializer actually exports."""
    names = set(_PUBLIC_MODULE_TAILS)
    init = APP_ROOT / "modules" / module_name / "__init__.py"
    if not init.is_file():
        return frozenset(names)
    tree = ast.parse(init.read_text(), filename=str(init))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "_EXPORTS" and isinstance(node.value, ast.Dict):
                names.update(
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
            elif target.id in {"__all__", "_MODULE_EXPORTS"} and isinstance(
                node.value, ast.List | ast.Tuple
            ):
                names.update(
                    item.value
                    for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
    return frozenset(names)


def _foreign_module_import_violations(tree: ast.AST, *, owner: str, label: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        bindings: list[tuple[str, str | None]]
        if isinstance(node, ast.Import):
            bindings = [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            bindings = [(node.module, alias.name) for alias in node.names]
        else:
            continue
        for module_name, symbol in bindings:
            if not module_name.startswith("app.modules."):
                continue
            parts = module_name.removeprefix("app.modules.").split(".")
            other = parts[0]
            if other == owner:
                continue
            if len(parts) == 1:
                if symbol is None:
                    continue
                if symbol == "*" or symbol not in _package_public_names(other):
                    violations.append(f"{label} imports {symbol} from {module_name}")
                continue
            if parts[1] in _PUBLIC_MODULE_TAILS:
                continue
            # A package may declare submodules public (``_MODULE_EXPORTS``,
            # dotted for nested ones such as ``tools.extract``).
            if ".".join(parts[1:]) not in _package_public_names(other):
                violations.append(f"{label} imports {module_name}")
    return violations


def served_paths() -> set[str]:
    """Every HTTP path the app serves, read from its OpenAPI document.

    FastAPI 0.14x wraps each included router, so ``app.routes`` lists only the docs
    routes, and a "this route is gone" check over it passed whatever the app served.
    """
    from app.main import app

    return set(app.openapi()["paths"])
