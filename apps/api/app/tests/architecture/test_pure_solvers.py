"""Subject calculation code is pure, and the subjects meet only at public files.

A solver, catalog or extractor turns text and numbers into an answer. It never reaches a
database, a cache, the network or the web framework, so it runs anywhere: in a SymPy
worker, in a test, in a sweep. The edges that do (each subject's ``api``, the camera and
LLM readers, ``math/tool.py``, ``chemistry/context.py``) are outside these packages.
"""

from .boundary_support import APP_ROOT, _infrastructure_reached, _module_imports

PURE_PACKAGES: tuple[str, ...] = (
    "app.modules.math.match",
    "app.modules.math.solve",
    "app.modules.math.tools.block",
    "app.modules.math.tools.extractors",
    "app.modules.math.tools.school",
    "app.modules.physics.catalog",
    "app.modules.physics.extractors",
    "app.modules.physics.solvers",
    "app.modules.physics.symbolic",
    "app.modules.chemistry.extractors",
    "app.modules.chemistry.solvers",
    "app.services.law_binding",
)
SUBJECTS = frozenset({"chemistry", "math", "physics"})
# Besides the package itself, whose exported names the module-boundary test checks.
SUBJECT_PUBLIC_FILES = frozenset({"api", "schemas", "service"})


def test_infrastructure_check_finds_the_chemistry_cache_and_gateway_edge() -> None:
    reached = _infrastructure_reached(("app.modules.chemistry",))
    assert "app.modules.chemistry.context imports redis, app.gateways" in reached


def test_pure_calculation_packages_reach_no_infrastructure() -> None:
    for package in PURE_PACKAGES:
        assert (APP_ROOT.parent / package.replace(".", "/") / "__init__.py").is_file(), package
    violations = _infrastructure_reached(PURE_PACKAGES)
    assert not violations, "\n".join(violations)


def test_subjects_import_one_another_only_through_public_files() -> None:
    """Math, physics and chemistry are peers: none reaches into another's solvers or seams."""
    imports = _module_imports(load_time=False)
    violations: list[str] = []
    for module, targets in sorted(imports.items()):
        owner = module.split(".")
        if owner[:2] != ["app", "modules"] or len(owner) < 3 or owner[2] not in SUBJECTS:
            continue
        for target in sorted(targets & imports.keys()):
            parts = target.split(".")
            if (
                parts[:2] == ["app", "modules"]
                and len(parts) > 3
                and parts[2] in SUBJECTS - {owner[2]}
                and parts[3] not in SUBJECT_PUBLIC_FILES
            ):
                violations.append(f"{module} imports {target}")
    assert not violations, "\n".join(violations)
