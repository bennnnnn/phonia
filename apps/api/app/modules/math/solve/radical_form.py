"""A radical answer in simplest radical form: one radical per index, in book order.

``x^(5/3)`` prints as ``x∛(x²)`` and ``2√3·x^(3/2)`` as ``2x√(3x)``. SymPy keeps powers
fractional and folds ``x·√x`` straight back into ``x^(3/2)``, so the form is built
unevaluated and printed with ``order="none"``; each sum and product is rebuilt in the order
SymPy itself would print it.
"""

from __future__ import annotations

from typing import Any

from sympy import Add, Expr, Mul, Pow, Rational, latex, preorder_traversal


def has_radical(expr: Expr) -> bool:
    return any(node.exp.is_Rational and not node.exp.is_Integer for node in expr.atoms(Pow))


def book_radicals_latex(expr: Any) -> str | None:
    """The LaTeX in simplest radical form; None when SymPy's own already is."""
    if not _needs_rewrite(expr):
        return None
    return str(latex(_book_form(expr), order="none"))


def _root_part(factor: Any) -> bool:
    """A power to fold under a radical: ``x^(3/2)``, ``2^(1/3)``, never ``x^(-1/2)``."""
    return bool(
        factor.is_Pow
        and factor.exp.is_Rational
        and factor.exp.q > 1
        and factor.exp.p > 0
        and (factor.base.is_Symbol or (factor.base.is_Integer and factor.base > 0))
    )


def _needs_rewrite(expr: Any) -> bool:
    """Anywhere in it, a letter with a fractional power above 1 (``x^(2/3)`` in a
    denominator too), or two radicals of one index in one product."""
    if any(_root_part(node) and node.base.is_Symbol and node.exp.p > 1 for node in expr.atoms(Pow)):
        return True
    for node in preorder_traversal(expr):
        if node.is_Mul:
            indices = [int(root.exp.q) for root in node.args if _root_part(root)]
            if len(indices) != len(set(indices)):
                return True
    return False


def _book_form(expr: Any) -> Any:
    """Every node rebuilt in the order SymPy prints it, since ``order="none"`` prints the
    tree as built: ``|3x - √3|`` and ``(x - 1)``, never ``|-√3 + 3x|`` or ``(-1 + x)``."""
    if expr.is_Add:
        return Add(*(_book_form(term) for term in expr.as_ordered_terms()), evaluate=False)
    if expr.is_Mul or _root_part(expr):
        return _radical_product(Mul.make_args(expr) if expr.is_Mul else (expr,))
    if expr.is_Pow:
        return Pow(_book_form(expr.base), expr.exp, evaluate=False)
    if expr.args and expr.is_Function:
        return expr.func(*(_book_form(arg) for arg in expr.args), evaluate=False)
    return expr


def _radical_product(factors: tuple[Any, ...]) -> Any:
    # The coefficient whole: ``as_ordered_factors`` alone splits -3 into (-1)·3.
    coefficient, rest = Mul(*factors).as_coeff_Mul()
    outside: list[Any] = [] if coefficient == 1 else [coefficient]
    radicands: dict[int, list[Any]] = {}
    for factor in rest.as_ordered_factors():
        if not _root_part(factor):
            outside.append(_book_form(factor))
            continue
        index = int(factor.exp.q)
        whole, part = divmod(int(factor.exp.p), index)
        if whole:
            outside.append(factor.base**whole)
        if part:
            radicands.setdefault(index, []).append(_book_form(factor.base**part))
    roots = [
        Pow(_in_order(parts), Rational(1, index), evaluate=False)
        for index, parts in sorted(radicands.items())
    ]
    pieces = [*outside, *roots]
    return pieces[0] if len(pieces) == 1 else Mul(*pieces, evaluate=False)


def _in_order(parts: list[Any]) -> Any:
    """Numbers first, then letters alphabetically: ``√(3xy)``, never ``√(y x)``."""
    ordered = sorted(parts, key=lambda part: (not part.is_number, str(part)))
    return ordered[0] if len(ordered) == 1 else Mul(*ordered, evaluate=False)
