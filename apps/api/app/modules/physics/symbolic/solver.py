"""Bounded symbolic operations with residual checks and honest model assumptions."""

from __future__ import annotations

from typing import Any

import sympy as sp

from app.core.sympy_notation import use_school_log_notation
from app.modules.physics.schemas.symbolic import SymbolicPhysicsRequest
from app.modules.physics.symbolic.parse import ModelParser
from app.services.solving import SolveServiceError, VerifiedPhysicsBlock, wrap_verified_physics
from app.services.workout import Workout, math_line, render_workout, text_line

# ``log`` reads as base 10, so a natural log has to print as ``\ln``.
use_school_log_notation()

MAX_OUTPUT = 4000
_MODEL_NOTE = (
    "The calculation uses your stated model. Symbols have no assumed sign or units; "
    "complex solutions are retained. Vector operations use Cartesian coordinates."
)


def _plain(value: Any) -> str:
    return sp.sstr(list(value)) if isinstance(value, sp.MatrixBase) else sp.sstr(value)


def _nonzero_conditions(values: list[Any]) -> tuple[str, str]:
    conditions = sorted({sp.sstr(value) for value in values if value != sp.true})
    if any(value == sp.false for value in values):
        raise SolveServiceError("model has an undefined denominator")
    latex = sorted({sp.latex(value) for value in values if value != sp.true})
    return ", ".join(conditions), r",\quad ".join(latex)


def _solve(request: SymbolicPhysicsRequest, parser: ModelParser) -> list[Any]:
    targets = [parser.symbol(name) for name in request.variables]
    equations = [parser.equation(expression) for expression in request.expressions]
    if any(
        target not in set().union(*(equation.free_symbols for equation in equations))
        for target in targets
    ):
        raise SolveServiceError("every target must occur in the stated equations")
    for equation in equations:
        numerator = sp.together(equation).as_numer_denom()[0]
        if not numerator.is_polynomial(*targets) or sp.Poly(numerator, *targets).total_degree() > 4:
            raise SolveServiceError("only algebraic systems of degree at most four are supported")
    parameters = set().union(*(equation.free_symbols for equation in equations)) - set(targets)
    if parameters:
        # A residual check proves that a root works, not that the root set is
        # complete at every parameter value. Restrict parameterized systems to
        # affine equations with fixed coefficients, whose rank cannot change.
        # Keep the original equations: clearing F/m would introduce an m
        # coefficient even though the stated denominator already excludes m=0.
        for equation in equations:
            try:
                polynomial = sp.Poly(equation, *targets)
            except sp.PolynomialError as exc:
                raise SolveServiceError("parameterized algebra requires affine equations") from exc
            if polynomial.total_degree() > 1 or any(
                coefficient.free_symbols & parameters
                for powers, coefficient in polynomial.terms()
                if any(powers)
            ):
                raise SolveServiceError("parameter-dependent algebra requires singular branches")
    solutions = sp.solve(equations, targets, dict=True, check=True)
    if not solutions or len(solutions) > 8:
        raise SolveServiceError("no bounded explicit solution set")
    answers = []
    for solution in solutions:
        if any(target not in solution for target in targets):
            raise SolveServiceError("the system does not determine every requested target")
        if any(
            sp.simplify(equation.subs(solution, simultaneous=True)) != 0 for equation in equations
        ):
            raise SolveServiceError("a solution failed substitution into the model")
        conditions = [
            condition.subs(solution, simultaneous=True) for condition in parser.conditions
        ]
        conditions.extend(sp.Ne(sp.denom(sp.together(value)), 0) for value in solution.values())
        if any(condition == sp.false for condition in conditions):
            continue
        plain_condition, latex_condition = _nonzero_conditions(conditions)
        pairs = [sp.Eq(target, solution[target], evaluate=False) for target in targets]
        plain = ", ".join(sp.sstr(pair) for pair in pairs)
        latex = r",\quad ".join(sp.latex(pair) for pair in pairs)
        if plain_condition:
            plain += f" where {plain_condition}"
            latex += r"\quad\text{where }" + latex_condition
        answers.append((plain, latex))
    if not answers:
        raise SolveServiceError("all solutions violate the model domain")
    return answers


def _ode(request: SymbolicPhysicsRequest, parser: ModelParser) -> Any:
    variable = parser.symbol(request.variables[0])
    function = sp.Function(request.dependent)(variable)
    equation = parser.equation(request.expressions[0])
    order = sp.ode_order(equation, function)
    if order not in {1, 2}:
        raise SolveServiceError("only first and second order ODEs are supported")
    terms = [function, *(sp.diff(function, variable, degree) for degree in range(1, order + 1))]
    try:
        polynomial = sp.Poly(equation, *terms)
    except sp.PolynomialError as exc:
        raise SolveServiceError("only linear ODEs are supported") from exc
    if polynomial.total_degree() != 1:
        raise SolveServiceError("only linear ODEs are supported")
    coefficients = [polynomial.coeff_monomial(term) for term in terms]
    leading = coefficients[-1]
    parser.conditions.append(sp.Ne(leading, 0))
    # Parameter-dependent variable coefficients can have exceptional orders
    # and domains that a generic residual check does not establish.
    parameters = set().union(*(coefficient.free_symbols for coefficient in coefficients)) - {
        variable
    }
    if parameters and any(variable in coefficient.free_symbols for coefficient in coefficients):
        raise SolveServiceError("parameterized ODEs require constant coefficients")
    if order == 2 and parameters:
        constant, first, second = coefficients
        discriminant = sp.simplify(first**2 - 4 * second * constant)
        if discriminant != 0:
            parser.conditions.append(sp.Ne(discriminant, 0))
    solution = sp.dsolve(equation, function)
    if not isinstance(solution, sp.Equality) or solution.lhs != function:
        raise SolveServiceError("an explicit ODE solution is required")
    checked, _residual = sp.checkodesol(equation, solution, func=function)
    if not checked:
        raise SolveServiceError("ODE solution failed its residual check")
    # dsolve may introduce singularities absent from the input's divisions:
    # t*x'+x=0 -> C1/t. Record them on the published general family.
    parser.conditions.append(sp.Ne(sp.denom(sp.together(solution.rhs)), 0))
    for power in solution.rhs.atoms(sp.Pow):
        if power.exp.is_negative:
            parser.conditions.append(sp.Ne(power.base, 0))
    for logarithm in solution.rhs.atoms(sp.log):
        parser.conditions.append(sp.Ne(logarithm.args[0], 0))
    return solution


def _field(request: SymbolicPhysicsRequest, parser: ModelParser) -> Any:
    axes = [parser.symbol(name) for name in request.variables]
    if request.operation in {"gradient", "laplacian"}:
        field = parser.scalar(request.expressions[0])
        if request.operation == "gradient":
            return sp.Matrix([sp.diff(field, axis) for axis in axes])
        return sum(sp.diff(field, axis, 2) for axis in axes)
    field = parser.vector(request.expressions[0])
    if request.operation == "divergence":
        return sum(sp.diff(field[index], axis) for index, axis in enumerate(axes))
    return sp.Matrix(
        [
            sp.diff(field[2], axes[1]) - sp.diff(field[1], axes[2]),
            sp.diff(field[0], axes[2]) - sp.diff(field[2], axes[0]),
            sp.diff(field[1], axes[0]) - sp.diff(field[0], axes[1]),
        ]
    )


def _matrix(request: SymbolicPhysicsRequest, parser: ModelParser) -> list[Any]:
    matrix = parser.matrix(request.expressions[0])
    if matrix.free_symbols:
        raise SolveServiceError(
            "eigensystems require numeric entries; parameter branches unsupported"
        )
    values = matrix.eigenvects()
    if sum(multiplicity for _, multiplicity, _ in values) != matrix.rows:
        raise SolveServiceError("the eigenspectrum is incomplete")
    answers = []
    for value, multiplicity, vectors in values:
        if sp.simplify(matrix.charpoly().as_expr().subs(matrix.charpoly().gen, value)) != 0:
            raise SolveServiceError("an eigenvalue failed its characteristic equation")
        plain = f"eigenvalue {sp.sstr(value)} (multiplicity {multiplicity})"
        latex = rf"\lambda = {sp.latex(value)}\quad\text{{(multiplicity {multiplicity})}}"
        if request.operation == "eigenvectors":
            for vector in vectors:
                residual = (matrix - value * sp.eye(matrix.rows)) * vector
                if any(sp.simplify(item) != 0 for item in residual):
                    raise SolveServiceError("an eigenvector failed its residual check")
            plain += "; basis " + ", ".join(_plain(vector) for vector in vectors)
            latex += r"\quad v = " + r",\quad ".join(sp.latex(vector) for vector in vectors)
        answers.append((plain, latex))
    return answers


def _calculate(request: SymbolicPhysicsRequest, parser: ModelParser) -> Any:
    operation = request.operation
    if operation == "ode":
        return _ode(request, parser)
    if operation in {"gradient", "divergence", "curl", "laplacian"}:
        return _field(request, parser)
    if operation in {"dot", "cross"}:
        left, right = [parser.vector(expression) for expression in request.expressions]
        return left.dot(right) if operation == "dot" else left.cross(right)
    expression = parser.scalar(request.expressions[0])
    if operation == "simplify":
        return sp.simplify(expression)
    variable = parser.symbol(request.variables[0])
    if operation == "differentiate":
        return sp.diff(expression, variable)
    if request.bounds:
        lower, upper = [parser.scalar(bound) for bound in request.bounds]
        if variable in lower.free_symbols | upper.free_symbols:
            raise SolveServiceError(
                "integration limits must not depend on the integration variable"
            )
        return sp.integrate(expression, (variable, lower, upper))
    integral = sp.integrate(expression, variable)
    if sp.simplify(sp.diff(integral, variable) - expression) != 0:
        raise SolveServiceError("antiderivative failed its derivative check")
    return integral + sp.Symbol("C1")


def build_symbolic_physics_block(
    request: SymbolicPhysicsRequest,
    text: str,
) -> VerifiedPhysicsBlock:
    """Run only in the existing bounded symbolic worker at the chat boundary."""
    parser = ModelParser(request.dependent, request.variables[0] if request.variables else None)
    if request.operation == "solve":
        answers = _solve(request, parser)
        conditions: tuple[str, str] = ("", "")
    elif request.operation in {"eigenvalues", "eigenvectors"}:
        answers = _matrix(request, parser)
        conditions = _nonzero_conditions(parser.conditions)
    else:
        result = _calculate(request, parser)
        if result.has(sp.Integral, sp.Derivative, sp.zoo, sp.nan, sp.oo, -sp.oo):
            raise SolveServiceError(
                "the symbolic calculation did not produce a finite explicit result"
            )
        answers = [(_plain(result), sp.latex(result))]
        conditions = _nonzero_conditions(parser.conditions)
    plain_joiner = " or " if request.operation == "solve" else "; "
    latex_joiner = r"\quad\text{or}\quad " if request.operation == "solve" else r",\quad "
    plain = plain_joiner.join(answer[0] for answer in answers)
    latex = latex_joiner.join(answer[1] for answer in answers)
    if max(len(plain), len(latex)) > MAX_OUTPUT:
        raise SolveServiceError("symbolic result too large for an answer card")
    # Keep model text literal; fence-injection characters fail the AST parser above.
    calculation = request.operation.capitalize() + (
        f" with respect to {', '.join(request.variables)}." if request.variables else "."
    )
    steps = [text_line(calculation), text_line(_MODEL_NOTE)]
    if conditions[0]:
        steps.append(math_line(conditions[1], "conditions"))
    workout = Workout(
        given=tuple(text_line(f"`{expression}`") for expression in request.expressions),
        steps=tuple(steps),
    )
    working = render_workout(workout).removesuffix("\n\n**Answer**")
    direct = render_workout(workout, latex)
    return VerifiedPhysicsBlock(
        text=wrap_verified_physics(f"{working}\n\nResult: {plain}"),
        canonical_answer=plain,
        display_answer=latex,
        canonical_fence={"type": "answer", "content": latex},
        domain_conditions=(conditions[0],) if conditions[0] else (),
        direct_reply=direct,
        direct_request_text=text,
        direct_answer_binding=latex,
        symbolic_request=request,
    )
