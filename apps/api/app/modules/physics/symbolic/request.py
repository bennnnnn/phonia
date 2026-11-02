"""Whole-request grammar; no model-generated equation or executable Python input."""

from __future__ import annotations

import re
from typing import cast

from app.modules.physics.schemas.symbolic import SymbolicOperation, SymbolicPhysicsRequest

MAX_SYMBOLIC_REQUEST = 2000
MAX_EXPRESSION = 512
_PREFIX = re.compile(r"\A\s*physics\s*:\s*", re.IGNORECASE)
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}\Z")
_COMMAND = re.compile(r"([a-z]+)\s+(.+)\Z", re.IGNORECASE | re.DOTALL)


def is_symbolic_physics_request(text: str) -> bool:
    return _PREFIX.match(text) is not None


def _variables(text: str) -> tuple[str, ...] | None:
    names = tuple(name.strip() for name in text.split(","))
    if not 1 <= len(names) <= 4 or len(set(names)) != len(names):
        return None
    if any(_NAME.fullmatch(name) is None for name in names):
        return None
    return names


def parse_symbolic_physics_request(text: str) -> SymbolicPhysicsRequest | None:
    if len(text) > MAX_SYMBOLIC_REQUEST:
        return None
    prefix = _PREFIX.match(text)
    if prefix is None:
        return None
    command = _COMMAND.fullmatch(text[prefix.end() :].strip())
    if command is None:
        return None
    operation, body = command[1].lower(), command[2].strip()
    variables: tuple[str, ...] = ()
    bounds: tuple[str, str] | None = None
    dependent: str | None = None
    if operation == "solve":
        parts = re.split(r"\s+for\s+", body, flags=re.IGNORECASE)
        if len(parts) != 2:
            return None
        body, targets = parts
        read = _variables(targets)
        if read is None:
            return None
        variables = read
    elif operation == "ode":
        match = re.fullmatch(
            r"(.+)\s+for\s+([A-Za-z][A-Za-z0-9_]{0,23})"
            r"\(([A-Za-z][A-Za-z0-9_]{0,23})\)",
            body,
            re.IGNORECASE,
        )
        if match is None or match[2] == match[3]:
            return None
        body, dependent, independent = match.groups()
        variables = (independent,)
    elif operation in {"differentiate", "integrate"}:
        parts = re.split(r"\s+with respect to\s+", body, flags=re.IGNORECASE)
        if len(parts) != 2:
            return None
        body, tail = parts
        if operation == "integrate":
            limits = re.fullmatch(r"(.+?)\s+from\s+(.+?)\s+to\s+(.+)", tail, re.IGNORECASE)
            if limits is not None:
                tail = limits[1]
                bounds = (limits[2].strip(), limits[3].strip())
        read = _variables(tail)
        if read is None or len(read) != 1:
            return None
        variables = read
    elif operation in {"gradient", "divergence", "curl", "laplacian"}:
        parts = re.split(r"\s+in\s+", body, flags=re.IGNORECASE)
        if len(parts) != 2:
            return None
        body, axes = parts
        read = _variables(axes)
        if read is None or len(read) != 3:
            return None
        variables = read
    elif operation not in {"simplify", "dot", "cross", "eigenvalues", "eigenvectors"}:
        return None
    expressions = tuple(expression.strip() for expression in body.split(";"))
    expected = 2 if operation in {"dot", "cross"} else 1
    if not expressions or len(expressions) > 4:
        return None
    if operation != "solve" and len(expressions) != expected:
        return None
    if any(not expression or len(expression) > MAX_EXPRESSION for expression in expressions):
        return None
    return SymbolicPhysicsRequest(
        operation=cast(SymbolicOperation, operation),
        expressions=expressions,
        variables=variables,
        bounds=bounds,
        dependent=dependent,
    )
