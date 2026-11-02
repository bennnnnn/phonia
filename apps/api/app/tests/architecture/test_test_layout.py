"""A test sits with what it tests (code-health audit TEST-10).

Module tests lived in top-level grab-bag files: 27 RevenueCat webhook tests in
``test_routers.py`` were not collected by ``pytest app/tests/modules/billing``, and a
module's tests could be anywhere. A top-level test file now tests a top-level app file
or the deploy; every other test goes in the folder of the code it tests
(``modules/<name>/``, ``core/``, ``gateways/``, ``services/``, ``routers/``, ...).
"""

from __future__ import annotations

from .boundary_support import APP_ROOT

_TESTS = APP_ROOT / "tests"
# Top-level test file -> the top-level code it tests.
_TOP_LEVEL = {
    "test_deploy_config.py": "fly.toml and the Dockerfile",
    "test_domain_errors.py": "app/exceptions.py: one body for every refusal",
    "test_error_codes_contract.py": "the error codes clients switch on, from every layer",
    "test_exceptions.py": "app/exceptions.py",
    "test_loop_guard.py": "app/tests/loop_guard.py, the suite's own guard",
    "test_main_lifespan.py": "app/main.py",
    "test_process_bootstrap.py": "app/process_bootstrap.py",
    "test_request_id.py": "app/main.py's middleware",
    "test_worker_health.py": "app/worker_health.py",
    "test_worker_main.py": "app/worker_main.py",
}


def test_top_level_test_files_test_top_level_code() -> None:
    found = {path.name for path in _TESTS.glob("test_*.py")}
    stray = sorted(found - set(_TOP_LEVEL))
    assert not stray, f"move these next to the code they test: {stray}"
    gone = sorted(set(_TOP_LEVEL) - found)
    assert not gone, f"take these off the list: {gone}"
