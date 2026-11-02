"""Exact model operations and whole-request, presentation, and worker boundaries."""

from __future__ import annotations

from dataclasses import replace

import pytest
import sympy as sp

from app.core.config import Settings
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.prompt import build_physics_augmentation
from app.modules.physics.symbolic.request import parse_symbolic_physics_request
from app.modules.physics.symbolic.solver import build_symbolic_physics_block
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject


def solve(text: str):
    request = parse_symbolic_physics_request(text)
    assert request is not None
    return build_symbolic_physics_block(request, text)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Physics: solve a=F/m for a", "Eq(a, F/m) where Ne(m, 0)"),
        ("Physics: solve x+y=a; x-y=b for x,y", "Eq(x, a/2 + b/2), Eq(y, a/2 - b/2)"),
        ("Physics: solve F=m*a; F=12; m=3 for F,m,a", "Eq(F, 12), Eq(m, 3), Eq(a, 4)"),
        ("Physics: differentiate A*cos(omega*t) with respect to t", "-A*omega*sin(omega*t)"),
        ("Physics: differentiate 3 with respect to t", "0"),
        ("Physics: integrate k*x with respect to x from 0 to L", "L**2*k/2"),
        ("Physics: integrate 2*t with respect to t", "C1 + t**2"),
        ("Physics: simplify sin(theta)^2+cos(theta)^2", "1"),
        ("Physics: gradient x^2+y^2+z^2 in x,y,z", "[2*x, 2*y, 2*z]"),
        ("Physics: divergence [x,y,z] in x,y,z", "3"),
        ("Physics: curl [-y,x,0] in x,y,z", "[0, 0, 2]"),
        ("Physics: laplacian x^2+y^2+z^2 in x,y,z", "6"),
        ("Physics: dot [1,2,3]; [4,5,6]", "32"),
        ("Physics: cross [1,0,0]; [0,1,0]", "[0, 0, 1]"),
        # School notation, as in math: log is base 10, ln is natural.
        ("Physics: simplify log(1000)", "3"),
        ("Physics: simplify ln(exp(2))", "2"),
    ],
)
def test_exact_model_operations(text: str, expected: str) -> None:
    assert detect_subject(text) == "physics"
    block = solve(text)
    assert block.canonical_answer == expected
    assert maybe_direct_physics_reply(block, text) is not None


def test_ode_general_solution_is_checked() -> None:
    block = solve("Physics: ode x''+4*x=0 for x(t)")
    assert "C1*sin(2*t) + C2*cos(2*t)" in block.canonical_answer
    first_order = solve("Physics: ode v'+2*v=0 for v(t)")
    assert "C1*exp(-2*t)" in first_order.canonical_answer


def test_eigenvalues_and_eigenspaces() -> None:
    block = solve("Physics: eigenvectors [[2,0],[0,3]]")
    assert "eigenvalue 2 (multiplicity 1)" in block.canonical_answer
    assert "eigenvalue 3 (multiplicity 1)" in block.canonical_answer
    assert "basis [1, 0]" in block.canonical_answer
    repeated = solve("Physics: eigenvalues [[2,0],[0,2]]")
    assert "multiplicity 2" in repeated.canonical_answer


def test_decimal_source_lexemes_remain_exact() -> None:
    assert solve("Physics: simplify 9007199254740993.0").canonical_answer == "9007199254740993"
    assert (
        solve("Physics: simplify 10000000000000000.1-10000000000000000").canonical_answer == "1/10"
    )
    assert solve("Physics: solve x=0.100000000000000000001 for x").canonical_answer == (
        "Eq(x, 100000000000000000001/1000000000000000000000)"
    )
    assert solve("Physics: simplify 1e-100").canonical_answer == str(sp.Rational("1e-100"))


def test_ode_general_family_states_its_generated_domain_and_parameter_conditions() -> None:
    singular = solve("Physics: ode t*x'+x=0 for x(t)")
    assert "Ne(t, 0)" in singular.domain_conditions[0]
    parameterized = solve("Physics: ode m*x''+k*x=0 for x(t)")
    assert "Ne(m, 0)" in parameterized.domain_conditions[0]
    assert "Ne(-4*k*m, 0)" in parameterized.domain_conditions[0]
    repeated = solve("Physics: ode x''+2*x'+x=0 for x(t)")
    assert "C2*t" in repeated.canonical_answer
    first_order = solve("Physics: ode a*x'+x=0 for x(t)")
    assert "Ne(a, 0)" in first_order.domain_conditions[0]
    assert r"a \neq 0" in first_order.text


def test_algebra_retains_branches_and_denominator_conditions() -> None:
    roots = solve("Physics: solve v^2=4 for v")
    assert "Eq(v, -2)" in roots.canonical_answer
    assert "Eq(v, 2)" in roots.canonical_answer
    complex_roots = solve("Physics: solve v^2=-1 for v")
    assert "-I" in complex_roots.canonical_answer
    assert "complex solutions are retained" in complex_roots.text
    cancelled = solve("Physics: solve x/x+x=2 for x")
    assert cancelled.canonical_answer == "Eq(x, 1)"
    with pytest.raises(SolveServiceError):
        solve("Physics: solve x/x+x=1 for x")


@pytest.mark.parametrize(
    "text",
    [
        "Physics: solve F=m*a for a and explain friction",
        "Physics: solve F=m*a for a; also compute work",
        "Physics: differentiate t^2 with respect to t then find speed",
        "Physics: integrate t from 0 to 2",
        "Physics: gradient x in x,y",
        "Physics: solve x=1 for x,x",
        "Physics: dot [1,0,0]",
        "Physics: execute print(1)",
        "Physics: " + "x" * 2000,
    ],
)
def test_whole_request_grammar_declines_extra_work(text: str) -> None:
    assert parse_symbolic_physics_request(text) is None


@pytest.mark.parametrize(
    "body",
    [
        "simplify __import__('os').getcwd()",
        "simplify x.__class__",
        "simplify [x for x in range(3)]",
        "simplify 2**1000",
        "simplify 1e999",
        "simplify (lambda x:x)(2)",
        "simplify True",
        "simplify 1/0",
        "simplify x # also solve y",
        "solve a*x=0 for x",
        "solve F=m*a for a",
        "solve a*x+y=0; x+a*y=0 for x,y",
        "solve x^3+a*x=0 for x",
        "solve sin(t)=0 for t",
        "solve x^5-x+1=0 for x",
        "solve x=1 for y",
        "solve x+y=2 for x,y",
        "integrate exp(t^3) with respect to t from 0 to t",
        "eigenvalues [[1,2,3],[1,2,3]]",
        "eigenvectors [[a,b],[0,a]]",
        "eigenvectors [[0,1],[a,0]]",
        "cross [1,2]; [2,3]",
        "ode x'''=0 for x(t)",
        "ode DerivativeOne+x=0 for x(t)",
        "ode t*x'+a*x=0 for x(t)",
        "ode x'+x^2=0 for x(t)",
    ],
)
def test_unsupported_or_unsafe_models_never_verify(body: str) -> None:
    with pytest.raises((SolveServiceError, TypeError, ValueError)):
        solve("Physics: " + body)


def test_symbolic_direct_reply_is_bound_to_request_and_card() -> None:
    text = "Physics: solve a=F/m for a"
    block = solve(text)
    assert maybe_direct_physics_reply(block, text + " and find work") is None
    assert maybe_direct_physics_reply(block, text, has_image_attachment=True) is None
    assert maybe_direct_physics_reply(replace(block, display_answer="wrong"), text) is None
    assert maybe_direct_physics_reply(replace(block, allow_direct=False), text) is None


@pytest.mark.asyncio
async def test_symbolic_boundary_uses_worker_timeout_and_declines(monkeypatch) -> None:
    settings = Settings(math_tools_enabled=True)
    calls = []

    async def worker(fn, *args, **kwargs):
        calls.append(kwargs["timeout"])
        return fn(*args)

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", worker)
    text = "Physics: solve a=F/m for a"
    _prompt, verified, failed = await build_physics_augmentation(text, settings)
    assert verified is not None and not failed
    assert calls == [settings.stem_solve_timeout_seconds]
    _prompt, verified, failed = await build_physics_augmentation(
        "Physics: solve sin(x)=0 for x",
        settings,
    )
    assert verified is None and failed

    async def timeout_worker(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", timeout_worker)
    _prompt, verified, failed = await build_physics_augmentation(text, settings)
    assert verified is None and failed
    assert await build_physics_augmentation(text, Settings(math_tools_enabled=False)) == (
        None,
        None,
        False,
    )
