"""SymPy MCP adapter."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.config import Settings
from app.gateways.mcp.base import ToolContext, ToolResult
from app.models.schemas.tools import SympyToolInput
from app.modules.math import solve as math_solve
from app.modules.math import tools as math_tools
from app.modules.math.schemas import (
    CircleGeometryBlockSpec,
    CircleGeometryInput,
    EquationInput,
    GeometryBlockSpec,
    GraphBlockSpec,
    GraphSampleInput,
    MathExprResult,
    NewtonMethodInput,
    RectangleGeometryInput,
    SquareGeometryInput,
    SystemOfEquationsInput,
)
from app.modules.math.solve.restated import REWRITES, card_restates
from app.modules.math.tools.calculus_outcome import infinite_integral_note, undefined_integral_note

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_ActionHandler = Callable[["SympyAdapter", dict[str, Any]], Awaitable[ToolResult]]


def _fence_data(
    canonical_fence: dict[str, Any] | None,
    *,
    canonical_answer: str | None = None,
) -> dict[str, Any] | None:
    """Attach canonical fence JSON for post-stream validate_math_fences."""
    data: dict[str, Any] = {}
    if canonical_fence is not None:
        data["canonical_fence"] = canonical_fence
    if canonical_answer:
        data["canonical_answer"] = canonical_answer
    return data or None


def _verified_content(body: str) -> str:
    return body.rstrip()


class SympyAdapter:
    name = "sympy"
    input_schema = SympyToolInput

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def describe(self) -> str:
        return (
            "Symbolic math: solve equations / systems / inequalities, simplify, "
            "differentiate, integrate (optional lower/upper for definite), factor, "
            "expand, limits, series, Newton's method, first-order ODEs (dsolve), "
            "rectangle/square/circle "
            "geometry, and graphs (optional second curve via expr2). In expressions log(x) "
            "is base 10, ln(x) is the natural log, and log(x, b) has base b."
        )

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.describe(),
                "parameters": SympyToolInput.model_json_schema(),
            },
        }

    async def _run_off_loop(self, fn: Callable[..., _T], *args: Any) -> _T | None:
        """Run synchronous, CPU-bound SymPy work in the bounded subprocess pool with a hard
        timeout + SIGTERM on timeout, as every chat-path SymPy call: a pathological expression
        sent through the model-callable "sympy" tool would otherwise stall every stream on
        this worker's event loop. A decline (``SolveServiceError``) is raised with its reason.

        The function and args must be picklable (top-level functions + plain data) so they
        can cross the subprocess boundary.
        """
        from app.core.sympy_executor import run_sympy

        try:
            return await run_sympy(fn, *args, timeout=self.settings.stem_solve_timeout_seconds)
        except math_solve.SolveServiceError:
            raise
        except TimeoutError:
            logger.warning("sympy MCP tool call timed out")
            return None
        except Exception:
            logger.warning("sympy MCP tool call failed", exc_info=True)
            return None

    async def _action_solve(self, args: dict[str, Any]) -> ToolResult:
        data = EquationInput(
            lhs=str(args.get("lhs") or ""),
            rhs=str(args.get("rhs") or ""),
            variables=list(args.get("variables") or ["x"]),
        )
        result = await self._run_off_loop(math_solve.solve_equation, data)
        if result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        # Parity with heuristic solve: attach ```answer for post-stream rewrite.
        answer = math_tools._format_equation_answer(
            result.canonical_solutions_latex or result.solutions_latex,
            result.solution_kind,
        )
        return ToolResult(
            name=self.name,
            content=_verified_content("\n".join(result.steps) + f"\nVerified result: {answer}"),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_expr_op(self, args: dict[str, Any]) -> ToolResult:
        action = str(args.get("action") or "").strip().lower()
        expr = str(args.get("expr") or "")
        variable = str(args.get("variable") or "x")
        expr_result: MathExprResult | None = None
        indefinite = action == "integrate"
        if action == "integrate":
            lower = str(args.get("lower") or args.get("start") or "").strip()
            upper = str(args.get("upper") or args.get("end") or "").strip()
            if bool(lower) != bool(upper):
                return ToolResult(
                    name=self.name, content="Math error: both integral bounds are required."
                )
            if lower and upper:
                indefinite = False
                expr_result = await self._run_off_loop(
                    math_solve.integrate_definite, expr, variable, lower, upper
                )
                if expr_result is None:
                    # A failed definite integral is not an indefinite-integral
                    # request. Do not silently solve a different problem.
                    return ToolResult(name=self.name, content="Math error: timed out.")
        if expr_result is None:
            if action == "diff":
                try:
                    order_n = int(args.get("order") or 1)
                except (TypeError, ValueError):
                    order_n = 1
                expr_result = await self._run_off_loop(
                    math_solve.differentiate_expression, expr, variable, order_n
                )
            else:
                fn = {
                    "simplify": math_solve.simplify_expression,
                    "integrate": math_solve.integrate_expression,
                    "factor": math_solve.factor_expression,
                    "expand": math_solve.expand_expression,
                }[action]
                expr_result = await self._run_off_loop(fn, expr, variable)
        if expr_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        integral_note = None
        if action == "integrate":
            undefined_note = undefined_integral_note(expr_result.result)
            if undefined_note is not None:
                return ToolResult(name=self.name, content=undefined_note)
            integral_note = infinite_integral_note(expr_result.result)
        # As the heuristic path: an integral SymPy could not close (a literal Integral(...)),
        # or a rewrite that only restates the expression (solve/restated.py), is NOT a
        # verified answer: an honesty note, and no ```answer fence for validate_math_fences.
        restated = action in REWRITES and await self._run_off_loop(
            card_restates, expr_result.latex, (expr,)
        )
        if not expr_result.solved or restated:
            return ToolResult(
                name=self.name,
                content=(
                    f"SymPy could not find a closed-form result (got: {expr_result.latex}). "
                    "Do NOT claim this as a verified answer — tell the user no closed form "
                    "was found (and why the integral is hard), or that the expression is "
                    "already in its simplest form, instead of asserting a solution."
                ),
            )
        # A canonical ```answer fence lets validate_math_fences correct the model's final
        # answer to the verified SymPy value, as _action_solve/_action_inequality do.
        answer = expr_result.latex
        if indefinite:
            answer += " + C"
        if integral_note is not None:
            return ToolResult(
                name=self.name,
                content=_verified_content(f"{integral_note}\nResult: {answer}"),
            )
        return ToolResult(
            name=self.name,
            content=_verified_content(f"Result: {answer}\nVerified result: {answer}"),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_inequality(self, args: dict[str, Any]) -> ToolResult:
        comparator = str(args.get("comparator") or "").strip()
        if comparator not in ("<", ">", "<=", ">="):
            return ToolResult(
                name=self.name,
                content='Math error: inequality requires comparator one of "<", ">", "<=", ">=".',
            )
        variables = list(args.get("variables") or ["x"])
        variable = str(args.get("variable") or (variables[0] if variables else "x"))
        result = await self._run_off_loop(
            math_solve.solve_inequality,
            str(args.get("lhs") or ""),
            str(args.get("rhs") or ""),
            variable,
            comparator,
        )
        if result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        answer = math_tools._format_equation_answer(result.solutions_latex, result.solution_kind)
        content = _verified_content("\n".join(result.steps) + f"\nVerified result: {answer}")
        data = _fence_data(math_tools._answer_canonical(answer), canonical_answer=answer)
        # Attach the verified number-line diagram — same invariant the
        # heuristic _verified_block_inequality enforces. Without this the
        # MCP inequality path returned only an ```answer fence, so the app
        # never rendered the solution set as an SVG and the model's own
        # (often malformed) ```graph fence shipped as-is.
        lhs = str(args.get("lhs") or "")
        rhs = str(args.get("rhs") or "")
        ineq_text = f"{lhs} {comparator} {rhs}"
        line_spec = await self._run_off_loop(
            math_solve.number_line_spec_from_expr, ineq_text, variable
        )
        if line_spec is not None:
            fence = line_spec.model_dump()
            content = _verified_content(
                "\n".join(result.steps) + f"\nVerified result: {answer}",
            )
            data = _fence_data(fence, canonical_answer=answer)
        return ToolResult(name=self.name, content=content, data=data)

    async def _action_system(self, args: dict[str, Any]) -> ToolResult:
        equations = [(str(lhs), str(rhs)) for lhs, rhs in (args.get("equations") or [])]
        system_input = SystemOfEquationsInput(
            equations=equations,
            variables=list(args.get("variables") or ["x", "y"]),
        )
        system_result = await self._run_off_loop(math_solve.solve_system, system_input)
        if system_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        answer = math_tools._format_system_answer(
            system_result.solutions, system_result.solution_kind
        )
        body = "\n".join(system_result.steps) + f"\nVerified result: {answer}"
        return ToolResult(
            name=self.name,
            content=_verified_content(body),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_limit(self, args: dict[str, Any]) -> ToolResult:
        expr = str(args.get("expr") or "")
        variable = str(args.get("variable") or "x")
        point = str(args.get("point") or "0")
        direction = str(args.get("direction") or "+-")
        limit_result = await self._run_off_loop(
            math_solve.compute_limit, expr, variable, point, direction
        )
        if limit_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        if limit_result.result == "zoo":
            return ToolResult(
                name=self.name,
                content=(
                    "The two-sided limit does not exist: the sides disagree. "
                    "Do not call it infinity."
                ),
            )
        # Parity with _verified_block_limit: attach a canonical ```answer
        # fence (the verified limit value) so validate_math_fences corrects
        # the model's final answer; flag an infinite limit so the model
        # renders \infty rather than treating it as a finite number.
        content = f"Result: {limit_result.latex}"
        if limit_result.is_infinite:
            content += (
                "\nThis limit is infinite — preserve its sign, do not treat it as an ordinary "
                "finite number."
            )
        answer = limit_result.latex
        return ToolResult(
            name=self.name,
            content=_verified_content(content),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_series(self, args: dict[str, Any]) -> ToolResult:
        expr = str(args.get("expr") or "")
        variable = str(args.get("variable") or "x")
        start = str(args.get("start") or "1")
        end = str(args.get("end") or "oo")
        series_result = await self._run_off_loop(
            math_solve.evaluate_series_sum, expr, variable, start, end
        )
        if series_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        # Parity with _verified_block_series: attach a canonical ```answer
        # fence (the verified sum value) so validate_math_fences corrects
        # the model's final answer; flag divergence to infinity explicitly.
        content = f"Result: {series_result.latex}"
        if series_result.is_convergent is not None:
            content += f"\nConvergent: {series_result.is_convergent}"
            if series_result.is_absolutely_convergent is not None:
                content += f" (absolutely convergent: {series_result.is_absolutely_convergent})"
            content += "."
        if series_result.is_convergent is False and not series_result.is_infinite:
            return ToolResult(
                name=self.name,
                content=content
                + "\nThis series diverges; it has no ordinary sum. Do not present a finite value.",
            )
        if not series_result.solved:
            return ToolResult(
                name=self.name,
                content=content + "\nThe sum was not evaluated. Do not claim a closed-form answer.",
            )
        if series_result.is_infinite:
            content += (
                "\nThis series diverges to infinity — preserve its sign, do "
                "not treat it as an ordinary finite number."
            )
        answer = series_result.latex
        return ToolResult(
            name=self.name,
            content=_verified_content(content),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_newton(self, args: dict[str, Any]) -> ToolResult:
        newton_input = NewtonMethodInput(
            expr=str(args.get("expr") or ""),
            variable=str(args.get("variable") or "x"),
            initial_guess=float(args.get("guess") or 1.0),
        )
        newton_result = await self._run_off_loop(math_solve.newton_method, newton_input)
        if newton_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        if not newton_result.converged or newton_result.root is None:
            return ToolResult(
                name=self.name,
                content=(
                    f"Newton's method did not converge "
                    f"(iterations={newton_result.iterations_used}). "
                    "Do NOT present a root as found."
                ),
            )
        answer = f"{newton_result.root:g}"
        return ToolResult(
            name=self.name,
            content=_verified_content(
                f"Newton's method: root={newton_result.root}, "
                f"converged={newton_result.converged}, "
                f"iterations={newton_result.iterations_used}\n"
                f"Verified result: {answer}"
            ),
            data=_fence_data(math_tools._answer_canonical(answer), canonical_answer=answer),
        )

    async def _action_rectangle(self, args: dict[str, Any]) -> ToolResult:
        rect_input = RectangleGeometryInput(
            width=float(args["width"]),
            height=float(args["height"]),
            unit=str(args.get("unit") or "cm"),
        )
        rect_result = await self._run_off_loop(math_solve.rectangle_geometry, rect_input)
        if rect_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        spec = GeometryBlockSpec(
            type="rectangle",
            width=rect_result.width,
            height=rect_result.height,
            unit=rect_result.unit,
            show_diagonal=True,
            show_angle=True,
            diagonal=rect_result.diagonal,
            angle_deg=rect_result.angle_deg,
            area=rect_result.area,
            perimeter=rect_result.perimeter,
            labels=rect_result.labels,
        )
        fence = spec.model_dump()
        return ToolResult(
            name=self.name,
            content=_verified_content(
                f"Rectangle {rect_result.width}x{rect_result.height} {rect_result.unit}: "
                f"diagonal={rect_result.diagonal}, angle={rect_result.angle_deg}°",
            ),
            data=_fence_data(fence),
        )

    async def _action_square(self, args: dict[str, Any]) -> ToolResult:
        side = args.get("side")
        if side is None:
            side = args.get("width")
        if side is None:
            return ToolResult(
                name=self.name,
                content="Math error: square requires side (or width).",
            )
        square_input = SquareGeometryInput(
            side=float(side),
            unit=str(args.get("unit") or "cm"),
        )
        square_result = await self._run_off_loop(math_solve.square_geometry, square_input)
        if square_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        spec = GeometryBlockSpec(
            type="square",
            side=square_result.side,
            width=square_result.side,
            height=square_result.side,
            unit=square_result.unit,
            show_diagonal=True,
            show_area=True,
            show_perimeter=True,
            diagonal=square_result.diagonal,
            area=square_result.area,
            perimeter=square_result.perimeter,
            labels=square_result.labels,
        )
        fence = spec.model_dump()
        return ToolResult(
            name=self.name,
            content=_verified_content(
                f"Square side={square_result.side:g} {square_result.unit}: "
                f"diagonal={square_result.diagonal:g}, area={square_result.area:g}",
            ),
            data=_fence_data(fence),
        )

    async def _action_circle(self, args: dict[str, Any]) -> ToolResult:
        if args.get("radius") is None:
            return ToolResult(
                name=self.name,
                content="Math error: circle requires radius.",
            )
        circle_input = CircleGeometryInput(
            radius=float(args["radius"]),
            unit=str(args.get("unit") or "cm"),
        )
        circle_result = await self._run_off_loop(math_solve.circle_geometry, circle_input)
        if circle_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        spec = CircleGeometryBlockSpec(
            type="circle",
            radius=circle_result.radius,
            unit=circle_result.unit,
            show_diameter=True,
            show_area=True,
            show_circumference=True,
            diameter=circle_result.diameter,
            area=circle_result.area,
            circumference=circle_result.circumference,
            labels=circle_result.labels,
        )
        fence = spec.model_dump()
        return ToolResult(
            name=self.name,
            content=_verified_content(
                f"Circle radius={circle_result.radius:g} {circle_result.unit}: "
                f"diameter={circle_result.diameter:g}, "
                f"area={circle_result.area:.2f}, "
                f"circumference={circle_result.circumference:.2f}",
            ),
            data=_fence_data(fence),
        )

    async def _action_graph(self, args: dict[str, Any]) -> ToolResult:
        variable = str(args.get("variable") or "x")
        x_min = float(args.get("x_min") or -10)
        x_max = float(args.get("x_max") or 10)
        n = self.settings.math_graph_max_points
        raw_expr = args.get("expr")
        if not isinstance(raw_expr, str) or not raw_expr.strip():
            return ToolResult(name=self.name, content="Math error: graph requires an expression.")
        expr = raw_expr.strip()

        # Axis-aligned circle/ellipse relations — parametric sample (not y=f(x)).
        # Shared with the heuristic _verified_block_graph so the sampling and
        # y-range viewport stay in one place (math_solve.build_ellipse_graph_spec).
        # Routed through the bounded subprocess pool like the original
        # sample_ellipse call was, so a pathological relation still can't
        # block the worker event loop.
        ellipse_spec = await self._run_off_loop(math_solve.build_ellipse_graph_spec, expr, n)
        if ellipse_spec is None or str(args.get("expr2") or "").strip():
            ellipse_spec = None
        if ellipse_spec is not None:
            fence = ellipse_spec.model_dump()
            return ToolResult(
                name=self.name,
                content=_verified_content(
                    f"Sampled {len(ellipse_spec.points)} parametric points for {ellipse_spec.expr}",
                ),
                data=_fence_data(fence),
            )

        line_spec = await self._run_off_loop(math_solve.number_line_spec_from_expr, expr, variable)
        if line_spec is not None and not str(args.get("expr2") or "").strip():
            fence = line_spec.model_dump()
            return ToolResult(
                name=self.name,
                content=_verified_content(
                    f"Shaded region for {line_spec.expr} on the number line "
                    "(open circle = not included).",
                ),
                data=_fence_data(fence),
            )

        graph_input = GraphSampleInput(
            expr=expr,
            variable=variable,
            x_min=x_min,
            x_max=x_max,
            n=n,
        )
        graph_result = await self._run_off_loop(math_solve.sample_function, graph_input)
        if graph_result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        has_discontinuity = len(graph_result.segments) > 1

        expr2_raw = str(args.get("expr2") or "").strip()
        expr2 = expr2_raw or None
        variable2 = None
        points2 = None
        segments2 = None
        label = str(args.get("label") or "").strip() or None
        label2 = str(args.get("label2") or "").strip() or None
        if expr2:
            var2 = str(args.get("variable2") or variable)
            sample2 = await self._run_off_loop(
                math_solve.sample_function,
                GraphSampleInput(
                    expr=expr2,
                    variable=var2,
                    x_min=x_min,
                    x_max=x_max,
                    n=n,
                ),
            )
            if sample2 is None:
                return ToolResult(name=self.name, content="Math error: timed out.")
            expr2 = sample2.expr
            variable2 = sample2.variable
            points2 = sample2.points
            segments2 = sample2.segments if len(sample2.segments) > 1 else []
            if label is None:
                label = f"y = {graph_result.expr}"
            if label2 is None:
                label2 = f"y = {sample2.expr}"

        graph_spec = GraphBlockSpec(
            expr=graph_result.expr,
            variable=graph_result.variable,
            x_min=graph_result.x_min,
            x_max=graph_result.x_max,
            points=graph_result.points,
            segments=graph_result.segments if has_discontinuity else [],
            expr2=expr2,
            variable2=variable2,
            points2=points2,
            segments2=segments2,
            label=label,
            label2=label2,
        )
        fence = graph_spec.model_dump()
        if expr2:
            summary = (
                f"Sampled {len(graph_result.points)} + {len(points2 or [])} points "
                f"for {graph_result.expr} and {expr2}\n"
            )
        else:
            summary = f"Sampled {len(graph_result.points)} points for {graph_result.expr}\n"
        return ToolResult(
            name=self.name,
            content=_verified_content(summary),
            data=_fence_data(fence),
        )

    async def _action_dsolve(self, args: dict[str, Any]) -> ToolResult:
        from app.modules.math.ode import solve_ode

        expr = str(args.get("expr") or args.get("text") or "")
        variable = str(args.get("variable") or "x")
        result = await self._run_off_loop(solve_ode, expr, variable)
        if result is None:
            return ToolResult(name=self.name, content="Math error: timed out.")
        return ToolResult(
            name=self.name,
            content=_verified_content(f"ODE: {result.latex}"),
            data=_fence_data(
                math_tools._answer_canonical(result.latex), canonical_answer=result.latex
            ),
        )

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "solve").strip().lower()
        try:
            handler = _ACTION_HANDLERS.get(action)
            if handler is not None:
                return await handler(self, args)
            intent = math_tools.extract_math_intent(str(args.get("text") or ""))
            if intent:
                block = await math_tools._build_verified_block_async(intent, self.settings)
                if block:
                    return ToolResult(
                        name=self.name,
                        content=block.text,
                        data=_fence_data(
                            block.canonical_fence,
                            canonical_answer=block.canonical_answer,
                        ),
                    )
            return ToolResult(name=self.name, content="No math result.")
        except Exception as exc:
            return ToolResult(name=self.name, content=f"Math error: {exc}")


_ACTION_HANDLERS: dict[str, _ActionHandler] = {
    "solve": SympyAdapter._action_solve,
    "simplify": SympyAdapter._action_expr_op,
    "diff": SympyAdapter._action_expr_op,
    "integrate": SympyAdapter._action_expr_op,
    "factor": SympyAdapter._action_expr_op,
    "expand": SympyAdapter._action_expr_op,
    "inequality": SympyAdapter._action_inequality,
    "system": SympyAdapter._action_system,
    "limit": SympyAdapter._action_limit,
    "series": SympyAdapter._action_series,
    "newton": SympyAdapter._action_newton,
    "dsolve": SympyAdapter._action_dsolve,
    "rectangle": SympyAdapter._action_rectangle,
    "square": SympyAdapter._action_square,
    "circle": SympyAdapter._action_circle,
    "graph": SympyAdapter._action_graph,
}
