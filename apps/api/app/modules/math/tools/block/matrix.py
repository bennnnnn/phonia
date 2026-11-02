"""Matrix verified blocks."""

from __future__ import annotations

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent, MatrixInput
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock


def _verified_block_matrix(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.matrix_op is None or not intent.matrix_rows:
        return None
    if intent.matrix_op == "inverse":
        determinant = math_solve.compute_matrix(
            MatrixInput(operation="determinant", rows=intent.matrix_rows)
        )
        if determinant.determinant == 0:
            lines.extend(determinant.steps)
            message = "This matrix has no inverse because its determinant is 0."
            lines.append(message)
            return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
    try:
        result = math_solve.compute_matrix(
            MatrixInput(
                operation=intent.matrix_op,
                rows=intent.matrix_rows,
                rows_b=intent.matrix_rows_b,
            )
        )
    except math_solve.SolveServiceError as exc:
        if intent.matrix_op == "diagonalize" and "not diagonalizable" in str(exc).lower():
            message = (
                "This matrix is not diagonalizable: it does not have enough "
                "linearly independent eigenvectors."
            )
            lines.append(message)
            return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
        raise
    lines.extend(result.steps)
    if result.operation == "inverse" and result.inverse_latex:
        answer = result.inverse_latex
    elif result.result_latex:
        answer = result.result_latex
    elif result.determinant is not None:
        answer = f"{result.determinant:g}"
    else:
        return VerifiedMathBlock(text="\n".join(lines))
    return finish_with_answer(
        lines,
        answer,
    )
