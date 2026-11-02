"""Verified chemistry prompt and direct-reply representation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Literal

from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers import ChemistryResult, solve_chemistry
from app.modules.chemistry.solvers.display import verified
from app.services.solving import SolveServiceError, VerifiedSolveBlock
from app.services.workout import WORKOUT_PROMPT_RULE, formula_heading

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class VerifiedChemistry(VerifiedSolveBlock):
    """Chemistry verified result on the same transport math and physics use."""

    subject: Literal["chemistry"] = "chemistry"
    intent: ChemistryIntent
    result: ChemistryResult

    @property
    def prompt_text(self) -> str:
        return self.text


def _bullet_rows(text: str) -> str:
    """One bullet per line. Chemistry rows are text, so the math splitter (which cuts at every
    ``=`` and comma) is not used: it turned ``x = 0.6`` / ``[N2O4] = 0.4`` into fragments."""
    return "\n".join(f"- {line.strip()}" for line in text.splitlines() if line.strip())


def _prompt_text(result: ChemistryResult) -> str:
    given = "\n".join(f"- {item}" for item in result.given)
    substitution = "\n".join(_bullet_rows(item) for item in result.substitution)
    # A procedure (balancing, a table lookup) has a rule, not an equation: its rows are Steps.
    # A law's name heads its equation (``formula_heading``): "Molar mass formula".
    if result.method:
        law, rows, law_line = "Formula", "Steps", f"Formula ({result.formula_name})"
    else:
        law = law_line = formula_heading(result.formula_name)
        rows = "Substitution"
    return (
        f"[{result.title}]\n"
        f"Use this visible layout: Given, Required, Solution, {law}, {rows}, Answer. "
        f"{WORKOUT_PROMPT_RULE} "
        "Do not write a prose wall, "
        "do not recalculate, and copy every verified number exactly: its trailing zeros are "
        "significant figures, so never add or drop one.\n"
        f"Given:\n{given}\n"
        f"Required:\n- {result.find}\n"
        f"{law_line}:\n{_bullet_rows(result.formula)}\n"
        f"{rows}:\n{substitution}\n"
        f"Verified answer:\n{_bullet_rows(result.answer)}\n"
        "Use the verified answer verbatim. Do not emit answer, smiles, or chem_scene fences."
    )


def build_verified_chemistry(intent: ChemistryIntent) -> VerifiedChemistry | None:
    try:
        result = solve_chemistry(intent)
    except SolveServiceError as exc:
        logger.info(
            "chemistry verification skipped kind=%s op=%s reason=%s",
            intent.kind,
            intent.chemistry_op,
            exc,
        )
        return None
    except Exception:
        logger.warning(
            "chemistry verification failed kind=%s op=%s",
            intent.kind,
            intent.chemistry_op,
            exc_info=True,
        )
        return None
    return VerifiedChemistry(
        text=_prompt_text(result),
        intent=intent,
        result=result,
        canonical_answer=result.answer.strip(),
    )


def verified_iupac(smiles: str, iupac_name: str) -> VerifiedChemistry:
    """A PubChem IUPACName that was actually returned. Not a local guess."""
    intent = ChemistryIntent(kind="organic", chemistry_op="iupac_name", formula=smiles)
    result = verified(
        "Verified IUPAC name",
        (smiles,),
        "IUPAC name",
        "PubChem IUPACName",
        "the IUPACName property for this SMILES",
        (iupac_name,),
        iupac_name,
        iupac_name,
        verbatim=True,
    )
    return VerifiedChemistry(
        text=_prompt_text(result),
        intent=intent,
        result=result,
        canonical_answer=result.answer.strip(),
    )


def verified_structure(
    name: str, smiles: str, formula: str, molar_mass: float
) -> VerifiedChemistry:
    """A named compound's structure from PubChem's SMILES; the server draws it, not the model.

    "Show me the structure of caffeine" got the SMILES as context and the model
    wrote it as garbled maths, or wrote one of its own. The structure fence is
    now the solver's, like an answer card: the model only describes it.
    """
    intent = ChemistryIntent(kind="organic", chemistry_op="structure", formula=smiles)
    result = replace(
        verified(
            f"Structure of {name}",
            (name,),
            "structure",
            "PubChem canonical SMILES",
            "the record PubChem returns for this name",
            (),
            "",
            "",
            verbatim=True,
        ),
        structure_smiles=smiles,
    )
    text = (
        f"[Verified structure of {name} (PubChem)]\n"
        f"Molecular formula: {formula}. Molar mass: {molar_mass:.2f} g/mol.\n"
        "Recall draws the structure under your reply from PubChem's SMILES. Do not write "
        "SMILES, a smiles fence, maths or ASCII art for it. Say in one to three sentences what "
        "the compound is and what the drawing shows (its rings and functional groups)."
    )
    return VerifiedChemistry(text=text, intent=intent, result=result, canonical_answer="")
