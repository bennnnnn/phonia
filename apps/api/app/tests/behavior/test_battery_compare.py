"""The battery's run record and the compare script, on synthetic runs (P12.5).

No live run is possible in CI; these check that a record holds what the compare
reads, and that the compare fails on each kind of regression and nothing else.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.tests.behavior.cases import CASES

_SCRIPTS = Path(__file__).resolve().parents[5] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_battery_{name}", _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compare_script = _load("battery_compare")


def _case(**overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "route": "model qwen-3.7-flash",
        "model": "qwen-3.7-flash",
        "misses": [],
        "error": None,
        "first_token_s": 0.8,
        "total_s": 2.0,
        "reply_chars": 400,
        "est_cost_usd": 0.0001,
    }
    case.update(overrides)
    return case


def _run(**cases: dict[str, Any]) -> dict[str, Any]:
    return {"meta": {"model": "auto", "sha": "abc1234"}, "cases": cases}


def test_identical_runs_have_no_regression() -> None:
    run = _run(hi=_case(), code=_case(route="model smart-chat", model="smart-chat"))
    result = compare_script.compare(run, json.loads(json.dumps(run)))
    assert result.regressions == [] and result.notes == [] and not result.failed


@pytest.mark.parametrize(
    "new, expected",
    [
        (_case(error="HTTP 500: boom"), "hi: now errors (HTTP 500: boom)"),
        (_case(misses=["did not search"]), "hi: now misses did not search"),
        (
            _case(route="searched (3 sources); model qwen-3.7-flash"),
            "hi: routing 'model qwen-3.7-flash' -> 'searched (3 sources); model qwen-3.7-flash'",
        ),
        (_case(model="glm-5.2"), "hi: model qwen-3.7-flash -> glm-5.2"),
        (_case(first_token_s=4.0), "hi: first token 0.8s -> 4.0s"),
    ],
)
def test_each_kind_of_regression_fails(new: dict[str, Any], expected: str) -> None:
    result = compare_script.compare(_run(hi=_case()), _run(hi=new))
    assert result.regressions == [expected]
    assert result.failed


def test_small_latency_wobbles_and_cost_changes_do_not_fail() -> None:
    result = compare_script.compare(
        _run(hi=_case(first_token_s=0.4)),
        _run(hi=_case(first_token_s=1.9, est_cost_usd=0.0003)),
    )
    assert result.regressions == []
    assert result.notes == ["hi: est. cost $0.00010 -> $0.00030"]


def test_an_error_that_is_fixed_is_not_a_regression() -> None:
    result = compare_script.compare(_run(hi=_case(error="timeout")), _run(hi=_case()))
    assert not result.failed


def test_cases_in_only_one_run_are_noted() -> None:
    result = compare_script.compare(_run(old=_case()), _run(new=_case()))
    assert result.notes == ["old: not in the new run", "new: new case"]
    assert not result.failed


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base, new, bad = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    base.write_text(json.dumps(_run(hi=_case())))
    new.write_text(json.dumps(_run(hi=_case(model="glm-5.2"))))
    bad.write_text("[]")
    assert compare_script.main([str(base), str(base)]) == 0
    assert compare_script.main([str(base), str(new)]) == 1
    assert "REGRESSION hi: model" in capsys.readouterr().out
    assert compare_script.main([str(base), str(bad)]) == 2


def test_the_battery_run_record_is_what_the_compare_reads() -> None:
    battery = _load("battery")
    case = next(c for c in CASES if c.id == "tone-plain")
    turn = battery.Turn(
        reply="Water helps your kidneys.",
        model="qwen-3.7-flash",
        first_token_s=0.81234,
        total_s=2.5,
        input_tokens=1_000,
        output_tokens=200,
    )
    record = battery.run_record([(case, turn)], model="auto", sha="abc1234", api="http://x")
    row = record["cases"]["tone-plain"]
    assert row["model"] == "qwen-3.7-flash"
    assert row["first_token_s"] == 0.81
    assert row["reply_chars"] == len(turn.reply)
    assert row["est_cost_usd"] == pytest.approx((1_000 * 0.03 + 200 * 0.13) / 1_000_000)
    assert row["misses"] == []
    assert record["meta"]["sha"] == "abc1234"
    assert not compare_script.compare(record, record).failed
