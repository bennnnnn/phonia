"""Keep the modular-monolith ownership rules executable during migration."""

import ast
import importlib
from pathlib import Path

from .boundary_support import (
    APP_ROOT,
    MOBILE_ROOT,
    _imports,
)


def test_todos_runtime_code_has_one_owner() -> None:
    module_root = APP_ROOT / "modules" / "todos"
    expected = {
        "actions.py",
        "api.py",
        "classification.py",
        "crud.py",
        "email_repository.py",
        "models.py",
        "prompt_context.py",
        "prompt_hint.py",
        "recurrence.py",
        "reminder_fences.py",
        "repository.py",
        "schedule_repository.py",
        "schemas.py",
    }
    assert expected <= {path.name for path in module_root.glob("*.py")}
    assert {
        "test_api.py",
        "test_email_repository.py",
        "test_recurrence.py",
        "test_repository.py",
        "test_schedule_repository.py",
        "test_schemas.py",
        "test_service.py",
        "test_unique_repository.py",
    } <= {path.name for path in (APP_ROOT / "tests" / "modules" / "todos").glob("*.py")}


def test_infrastructure_does_not_depend_on_product_modules() -> None:
    """Infrastructure imports no module, directly or through a ``models`` barrel.

    ``from app.models.orm import Memory`` reached memory's table and
    ``from app.models.schemas import MemoryFactOp`` its schema while this test only read
    the literal ``app.modules`` prefix (code-health audit ARCH-04); a barrel name now
    counts where it is defined.
    """
    violations: list[str] = []
    for layer in ("core", "gateways", "repositories"):
        for path in (APP_ROOT / layer).rglob("*.py"):
            for imported in _imports(path):
                if imported == "app.modules" or imported.startswith("app.modules."):
                    violations.append(f"{path.relative_to(APP_ROOT)} imports {imported}")
            for barrel, name in _barrel_names(path):
                defined_in = getattr(importlib.import_module(barrel), name).__module__
                if defined_in.startswith("app.modules."):
                    violations.append(
                        f"{path.relative_to(APP_ROOT)} imports {name} ({defined_in}) via {barrel}"
                    )
    assert not violations, "\n".join(violations)


def _barrel_names(path: Path) -> list[tuple[str, str]]:
    """``(barrel, name)`` for each name imported from ``app.models.orm`` or ``.schemas``."""
    found: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module in _BARRELS:
            found.extend((node.module, alias.name) for alias in node.names)
    return found


_BARRELS = frozenset({"app.models.orm", "app.models.schemas"})


def test_the_law_engine_does_not_depend_on_a_subject() -> None:
    """Physics and chemistry share ``services/law_binding``; it may import neither."""
    violations = [
        f"{path.relative_to(APP_ROOT)} imports {imported}"
        for path in (APP_ROOT / "services" / "law_binding").rglob("*.py")
        for imported in _imports(path)
        if imported == "app.modules" or imported.startswith("app.modules.")
    ]
    assert not violations, "\n".join(violations)


def test_mobile_todos_has_one_feature_home_and_thin_route() -> None:
    feature_root = MOBILE_ROOT / "features" / "todos"
    assert (feature_root / "api.ts").is_file()
    for folder in ("components", "context", "hooks", "model", "screens"):
        assert (feature_root / folder).is_dir()

    route = MOBILE_ROOT / "app" / "todos.tsx"
    lines = [line for line in route.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "features/todos/screens/TodosScreen" in lines[0]

    assert not (MOBILE_ROOT / "components" / "todos").exists()
    assert not (MOBILE_ROOT / "contexts" / "TodosContext.tsx").exists()
    assert not (MOBILE_ROOT / "lib" / "todos").exists()
    assert not (MOBILE_ROOT / "lib" / "api" / "todos.ts").exists()
    for name in (
        "useReminderBadgeCount.ts",
        "useTodoReminderState.ts",
        "useTodosActions.ts",
        "useTodosDerivedState.ts",
        "useTodosList.ts",
    ):
        assert not (MOBILE_ROOT / "hooks" / name).exists()

    feature_import_violations = [
        str(path.relative_to(MOBILE_ROOT))
        for path in feature_root.rglob("*.ts*")
        if "__tests__" not in path.parts and "@/app/" in path.read_text()
    ]
    assert not feature_import_violations


def test_memory_runtime_code_has_one_owner() -> None:
    module_root = APP_ROOT / "modules" / "memory"
    expected = {"api.py", "models.py", "ops.py", "repository.py", "schemas.py"}
    assert expected <= {path.name for path in module_root.glob("*.py")}
    assert (APP_ROOT / "tests" / "modules" / "memory" / "test_api.py").is_file()


def test_mobile_memory_has_one_feature_home_and_thin_routes() -> None:
    feature_root = MOBILE_ROOT / "features" / "memory"
    assert (feature_root / "api.ts").is_file()
    assert (feature_root / "types.ts").is_file()
    for folder in ("components", "hooks", "model", "screens"):
        assert (feature_root / folder).is_dir()

    route_targets = {
        MOBILE_ROOT / "app" / "memory" / "index.tsx": "MemoryScreen",
        MOBILE_ROOT / "app" / "memory" / "[key].tsx": "MemoryDocumentScreen",
        MOBILE_ROOT / "app" / "settings" / "memory-settings.tsx": "MemorySettingsScreen",
    }
    for route, screen in route_targets.items():
        lines = [line for line in route.read_text().splitlines() if line.strip()]
        assert len(lines) == 1
        assert f"features/memory/screens/{screen}" in lines[0]
    # One route home: the nested stack replaced the single memory.tsx route.
    assert not (MOBILE_ROOT / "app" / "memory.tsx").exists()

    assert not (MOBILE_ROOT / "components" / "memory").exists()
    assert not (MOBILE_ROOT / "lib" / "memoryFacts.ts").exists()
    assert not (MOBILE_ROOT / "lib" / "cache" / "memoryListCache.ts").exists()
    assert not (MOBILE_ROOT / "lib" / "api" / "memories.ts").exists()
    for name in ("useMemoryActions.ts", "useMemoryToggle.ts"):
        assert not (MOBILE_ROOT / "hooks" / name).exists()

    feature_import_violations = [
        str(path.relative_to(MOBILE_ROOT))
        for path in feature_root.rglob("*.ts*")
        if "__tests__" not in path.parts and "@/app/" in path.read_text()
    ]
    assert not feature_import_violations


def test_attachments_runtime_code_has_one_owner() -> None:
    module_root = APP_ROOT / "modules" / "attachments"
    expected = {
        "api.py",
        "chunks_repository.py",
        "jobs.py",
        "models.py",
        "reaper.py",
        "repository.py",
        "schemas.py",
    }
    assert expected <= {path.name for path in module_root.glob("*.py")}
    assert (APP_ROOT / "tests" / "modules" / "attachments" / "test_api.py").is_file()


def test_mobile_attachments_has_one_feature_home_and_thin_routes() -> None:
    feature_root = MOBILE_ROOT / "features" / "attachments"
    assert (feature_root / "api.ts").is_file()
    assert (feature_root / "types.ts").is_file()
    for folder in ("components", "hooks", "model", "screens"):
        assert (feature_root / folder).is_dir()

    route = MOBILE_ROOT / "app" / "gallery.tsx"
    lines = [line for line in route.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "features/attachments/screens/GalleryScreen" in lines[0]

    for gone in (
        MOBILE_ROOT / "lib" / "api" / "attachments.ts",
        MOBILE_ROOT / "lib" / "attachments.ts",
        MOBILE_ROOT / "lib" / "gallery.ts",
        MOBILE_ROOT / "lib" / "galleryLayout.ts",
        MOBILE_ROOT / "lib" / "cache" / "galleryListCache.ts",
        MOBILE_ROOT / "hooks" / "useGalleryData.ts",
        MOBILE_ROOT / "hooks" / "useGalleryLibrary.ts",
        MOBILE_ROOT / "hooks" / "useAttachmentIndexed.ts",
        MOBILE_ROOT / "components" / "GalleryThumbnail.tsx",
        MOBILE_ROOT / "components" / "AttachmentSourceSheet.tsx",
        MOBILE_ROOT / "components" / "gallery",
    ):
        assert not gone.exists(), gone

    feature_import_violations = [
        str(path.relative_to(MOBILE_ROOT))
        for path in feature_root.rglob("*.ts*")
        if "__tests__" not in path.parts and "@/app/" in path.read_text()
    ]
    assert not feature_import_violations


def test_images_runtime_code_has_one_owner() -> None:
    module_root = APP_ROOT / "modules" / "images"
    expected = {
        "api.py",
        "gen_intent.py",
        "gen_tool.py",
        "generation.py",
        "lookup_intent.py",
        "schemas.py",
        "search.py",
        "search_tool.py",
    }
    assert expected <= {path.name for path in module_root.glob("*.py")}
    assert (APP_ROOT / "tests" / "modules" / "images" / "test_api.py").is_file()

    # schemas.py imports MessageOut from chats, which loads this package first.
    # Re-exporting the image models here imports the module while it is still initializing.
    schema_barrel = APP_ROOT / "models" / "schemas" / "__init__.py"
    assert not any(
        imported == "app.modules.images" or imported.startswith("app.modules.images.")
        for imported in _imports(schema_barrel)
    )


def test_mobile_images_has_one_feature_home() -> None:
    feature_root = MOBILE_ROOT / "features" / "images"
    assert (feature_root / "api.ts").is_file()
    for folder in ("components", "hooks", "model"):
        assert (feature_root / folder).is_dir()

    for gone in (
        MOBILE_ROOT / "lib" / "api" / "images.ts",
        MOBILE_ROOT / "lib" / "images" / "imageGenIntent.ts",
        MOBILE_ROOT / "lib" / "images" / "imageLookupIntent.ts",
        MOBILE_ROOT / "lib" / "images" / "imageGenTurn.ts",
        MOBILE_ROOT / "hooks" / "useImageGeneration.ts",
        MOBILE_ROOT / "components" / "ImageGenPlaceholder.tsx",
        MOBILE_ROOT / "components" / "ImageGenPromptSheet.tsx",
        # Only the server reads image intent (POST /images/intent, ES-05).
        feature_root / "model" / "imageGenIntent.ts",
        feature_root / "model" / "imageGenIntentWords.ts",
        feature_root / "model" / "imageLookupIntent.ts",
        feature_root / "model" / "stemSubjectOwnsTurn.ts",
    ):
        assert not gone.exists(), gone
    assert (MOBILE_ROOT / "lib" / "images" / "imageUriPolicy.ts").is_file()

    feature_import_violations = [
        str(path.relative_to(MOBILE_ROOT))
        for path in feature_root.rglob("*.ts*")
        if "__tests__" not in path.parts and "@/app/" in path.read_text()
    ]
    assert not feature_import_violations


def test_speech_runtime_code_has_one_owner() -> None:
    module_root = APP_ROOT / "modules" / "speech"
    expected = {
        "api.py",
        "live_talk.py",
        "live_talk_tools.py",
        "realtime.py",
        "schemas.py",
        "service.py",
    }
    assert expected <= {path.name for path in module_root.glob("*.py")}
    assert (APP_ROOT / "tests" / "modules" / "speech" / "test_service.py").is_file()

    schema_barrel = APP_ROOT / "models" / "schemas" / "__init__.py"
    assert not any(
        imported == "app.modules.speech" or imported.startswith("app.modules.speech.")
        for imported in _imports(schema_barrel)
    )


def test_mobile_speech_has_one_feature_home() -> None:
    feature_root = MOBILE_ROOT / "features" / "speech"
    assert (feature_root / "api.ts").is_file()
    for folder in ("components", "hooks", "model"):
        assert (feature_root / folder).is_dir()

    for gone in (
        MOBILE_ROOT / "lib" / "api" / "speech.ts",
        MOBILE_ROOT / "hooks" / "useLiveTalk.ts",
        MOBILE_ROOT / "hooks" / "useVoiceInput.ts",
        MOBILE_ROOT / "lib" / "speech" / "pronunciation.ts",
        MOBILE_ROOT / "lib" / "speech" / "realtimeVoice.ts",
        MOBILE_ROOT / "components" / "chat" / "LiveTalkOverlay.tsx",
        MOBILE_ROOT / "components" / "chat" / "VoiceMicButton.tsx",
    ):
        assert not gone.exists(), gone
    assert (MOBILE_ROOT / "lib" / "speech" / "voiceAudio.ts").is_file()

    feature_import_violations = [
        str(path.relative_to(MOBILE_ROOT))
        for path in feature_root.rglob("*.ts*")
        if "__tests__" not in path.parts and "@/app/" in path.read_text()
    ]
    assert not feature_import_violations
