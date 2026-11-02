"""Exact scan-friendly replies for complete verified chemistry calculations."""

from __future__ import annotations

from collections.abc import Callable

from app.modules.chemistry.block import VerifiedChemistry
from app.modules.chemistry.extractors.atom_particles import asks_more_particles
from app.modules.chemistry.fence import assemble_chemistry_reply
from app.modules.chemistry.notation import typeset
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.question_parts import asks_more_parts
from app.services.student_claim import has_stated_result
from app.services.workout import Workout, formula_heading, render_workout, text_line


def _law_line(result: ChemistryResult, show: Callable[[str], str]) -> str:
    """A law's equation (its name heads it); a procedure's rule written out."""
    if result.method:
        return text_line(f"{result.formula_name}: {show(result.formula)}")
    return text_line(show(result.formula))


def format_direct_chemistry_reply(verified: VerifiedChemistry) -> str:
    result = verified.result
    # A lookup that only draws (a named compound's structure) computes nothing: no
    # Given/Required/Substitution, one line and the drawing.
    if result.structure_smiles and not result.answer.strip():
        return assemble_chemistry_reply(f"{result.title}, from PubChem:", verified)
    # The solver text is ASCII (H2SO4, Fe2+, ->); the reader gets H₂SO₄, Fe²⁺, →. A result
    # that carries SMILES or atom labels is left exactly as the solver wrote it.
    show = (lambda text: text) if result.verbatim else typeset
    # Chemistry rows stay text: a row like "n = 10 / 2.02 = 4.95 mol" is chemistry
    # notation, not a formula the client can typeset. The layout is the shared one.
    rows = tuple(text_line(show(line)) for line in result.substitution)
    workout = Workout(
        given=tuple(text_line(show(item)) for item in result.given),
        find=(text_line(show(result.find)),),
        formula=(_law_line(result, show),),
        # A law's name heads its equation ("Molar mass formula"); a procedure's
        # rule names itself on its line, under **Formula**.
        formula_heading=formula_heading(None if result.method else result.formula_name),
        # A procedure's rows check its rule (an atom tally, a range); they substitute nothing.
        steps=rows if result.method else (),
        substitution=() if result.method else rows,
    )
    return assemble_chemistry_reply(render_workout(workout), verified)


def maybe_direct_chemistry_reply(
    verified: VerifiedChemistry | None,
    *,
    has_image_attachment: bool,
    user_text: str = "",
) -> str | None:
    """Use exact output for typed text, and for a photo whose reading was confirmed.

    Not when the student stated a result to check: the model answers whether it is
    right, with the verified answer beside it. Not for a question in more labelled parts
    than the result answers either: the model answers them all.
    """
    if verified is None or has_stated_result(user_text):
        return None
    if asks_more_parts(user_text, verified.result.answer) or asks_more_particles(
        user_text, verified.result.answer
    ):
        return None
    if has_image_attachment:
        from app.modules.chemistry.reading import confirmed_chemistry_reading

        if confirmed_chemistry_reading(user_text) is None:
            return None
    return format_direct_chemistry_reply(verified)
