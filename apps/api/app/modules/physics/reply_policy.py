"""Physics prompt hints. A physics turn must not be told it is doing math."""

from app.services.workout import PHYSICS_WORKOUT_PROMPT_SHORT

PHYSICS_INTENT_HINT = (
    "Physics answers:\n"
    "  - This is a physics problem. Do not describe the work as math, algebra, "
    "or solving equations.\n"
    "  - When verified results appear in a [BEGIN VERIFIED PHYSICS] block, use "
    "those exact numbers and units. Do not recompute. If no verified block is "
    "present, do not claim verification.\n"
    "  - Never mention a system block, SymPy, or that a diagram will be attached.\n"
    f"  - For a concrete calculation: {PHYSICS_WORKOUT_PROMPT_SHORT} Equations in inline `$...$`.\n"
    "  - Do NOT emit ```answer, ```graph, ```simulation, or ```geometry.\n"
    "  - A trajectory is only for kinematics, projectile motion, or spring and "
    "pendulum motion. Every other answer is a number with units.\n"
    "  - If no verified block is present, still put the result under Answer "
    "in inline `$...$` with units. Never end on that heading. If there is no "
    "unique result, say what is missing "
    "instead of a blank Answer.\n"
    "  - Never join several transformations into one math row."
)

PHYSICS_SHORT_HINT = (
    "Physics in SHORT mode: give the result once, with units, in inline `$...$`. "
    "Do not describe the work as math. When a [BEGIN VERIFIED PHYSICS] block is "
    "present, use those exact numbers and do not recompute. Do NOT emit "
    "```answer, ```graph, ```simulation, or ```geometry. Never mention a system "
    "block or that a diagram will be attached. If no verified block is present, "
    "do not claim verification."
)

PHYSICS_REPLY_POLICY = (
    "Physics reply policy for this request: For a concrete calculation: "
    f"{PHYSICS_WORKOUT_PROMPT_SHORT} Put each value "
    "or equation on its own short line. One reasoning state per row; do not "
    "chain several equals signs. Head the formulas with the governing law's "
    "name before substituting. Do not add a math lesson, tutorial bullets, or Note/Tip "
    "cards. Copy verified numbers and units; do "
    "not recompute them. Honor SHORT by giving less, and DETAILED by showing "
    "the working. For a hint or practice, give a focused hint without the full "
    "solution unless the user asked for it. State the result once, on the "
    "Answer line, and never end on the heading."
)


# The symbols the server's own working shows (``notation``), so a reply the model
# writes reads the same as one the server writes.
PHYSICS_VELOCITY_NOTATION = (
    "Physics notation: write a body's initial and final velocity as $v_i$ and $v_f$ "
    "($v_f = v_i + at$, $v_f^2 = v_i^2 + 2as$), never u and v. In a collision, "
    "$v_{1i}$ and $v_{2i}$ before, $v_{1f}$ and $v_{2f}$ after."
)


def physics_prompt_hints(short: bool) -> tuple[str, ...]:
    """The physics pack: the short one in Short style or on a compact turn."""
    return (PHYSICS_SHORT_HINT,) if short else (PHYSICS_INTENT_HINT, PHYSICS_VELOCITY_NOTATION)
