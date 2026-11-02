"""Test helpers over the shared law-catalog expressions (``services.law_binding``)."""

from __future__ import annotations

import ast

from app.services.law_binding.expression import Notation, parse


def names(expression: str, notation: Notation) -> frozenset[str]:
    """The variable names an expression reads; functions and constants excluded."""
    tree = parse(expression)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return frozenset(
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id not in called
        and notation.constant(node.id) is None
    )
