"""Chemistry turn preparation: deterministic solve first, PubChem second."""

from __future__ import annotations

import asyncio
import logging
import re

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.sympy_executor import run_sympy
from app.gateways import pubchem_gateway
from app.modules import chemistry as chemistry_service
from app.modules.chemistry.block import (
    VerifiedChemistry,
    build_verified_chemistry,
    verified_iupac,
    verified_structure,
)
from app.modules.chemistry.elements import BY_NUMBER, ELEMENTS, Element
from app.modules.chemistry.equations import balance_equation, format_balanced
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.extractors.atom_particles import asks_more_particles
from app.modules.chemistry.input_text import read_chemistry_text
from app.modules.chemistry.request import (
    EQUATION_RE,
    extract_compound_name,
    is_chemistry_question,
)
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.smiles import MAX_SMILES_LENGTH
from app.services.question_parts import ONE_PART_NOTE, asks_more_parts
from app.services.workout import SELF_CHECK_PROMPT_RULE, WORKOUT_PROMPT_RULE

logger = logging.getLogger(__name__)

# PubChem is context, not a dependency: a slow lookup must not delay first token.
PUBCHEM_BUDGET_SECONDS = 2.0

_DESCRIPTOR_CUE = re.compile(
    r"\b(?:logp|log\s*p|tpsa|polar\s+surface\s+area|drug[-\s]?likeness|"
    r"hydrogen\s+bond|h[-\s]?bond|lipinski|ro5|bioavailability)\b",
    re.IGNORECASE,
)
_ELEMENT_CUE = re.compile(
    r"\b(?:atomic\s+(?:mass(?:es)?|numbers?|weights?)|electronegativit(?:y|ies)|"
    r"periodic\s+table|elements?|"
    r"electron\s+configuration|oxidation\s+states?|valence\s+electrons?)\b",
    re.IGNORECASE,
)
# Asks to see a named compound: its structure is drawn from PubChem, not written.
_SEE_STRUCTURE = re.compile(
    r"\b(?:structures?|draw|show|picture|diagram|skeletal|look\s+like|molecule\s+of)\b",
    re.IGNORECASE,
)
_IUPAC_SMILES = re.compile(r"\bIUPAC name\b[\s\S]{0,40}\bSMILES\s+(\S+)", re.IGNORECASE)
_STOICH_CUE = re.compile(
    r"\b(?:how\s+much|how\s+many|amount\s+of|moles\s+of|grams?\s+of|limiting\s+reagent)\b",
    re.IGNORECASE,
)
# British and IUPAC spellings the table (which follows the American ones) does not carry.
_ELEMENT_SPELLINGS = {"aluminium": "Al", "caesium": "Cs", "sulphur": "S"}
_ELEMENT_BY_NAME: dict[str, Element] = {
    **{element.name.lower(): element for element in ELEMENTS},
    **{
        spelling: next(e for e in ELEMENTS if e.symbol == symbol)
        for spelling, symbol in _ELEMENT_SPELLINGS.items()
    },
}
_SYMBOL_BY_TEXT: dict[str, Element] = {element.symbol: element for element in ELEMENTS}
# "carbon dioxide", "sodium chloride", "hydrogen bond": the element word names a compound or a
# bond, not the element.
_COMPOUND_FOLLOWERS = frozenset(
    {
        "oxide",
        "dioxide",
        "monoxide",
        "trioxide",
        "peroxide",
        "hydroxide",
        "chloride",
        "bromide",
        "iodide",
        "fluoride",
        "sulfide",
        "sulphide",
        "sulfate",
        "sulphate",
        "nitrate",
        "nitrite",
        "carbonate",
        "phosphate",
        "cyanide",
        "acid",
        "bond",
        "bonds",
        "bonding",
        "hydride",
    }
)
_WORD = re.compile(r"[A-Za-z]+")
_ATOMIC_NUMBER = re.compile(
    r"\b(?:atomic\s+number|element(?:\s+number)?)\s*(?:=|of|is)?\s*(\d{1,3})\b", re.IGNORECASE
)
# A bare symbol counts only where a symbol is being asked about ("mass of Fe", "symbol Cs"),
# never as a stray capital: the pronoun "I", "In group 1", "As a student". A digit after it
# ("of H2O") means a formula, not the element.
_SYMBOL_AFTER_CUE = re.compile(r"\b(?i:of|for|symbol|element)\s+([A-Z][a-z]?)(?![A-Za-z0-9])")
_MAX_ELEMENTS = 3
# Lexically valid SMILES only, so a sentence's words never reach RDKit.
_SMILES_TOKEN = re.compile(r"^(?:Cl|Br|[BCNOPSFI]|[bcnops]|\[[^\]\s]+\]|[=#$/\\()@+\-.%:]|\d)+$")
_MIN_SMILES_TOKEN = 3
_MAX_DESCRIPTOR_CANDIDATES = 8


def _stoichiometry_ratio_hint(content: str) -> str | None:
    """Preserve the useful verified ratio when a numeric amount is missing."""
    equation_match = EQUATION_RE.search(content)
    if equation_match is None or _STOICH_CUE.search(content) is None:
        return None
    equation = equation_match.group(1).strip()
    try:
        result = balance_equation(equation)
    except Exception:
        logger.info("stoichiometry ratio hint failed", exc_info=True)
        return None
    if not result.balanced:
        return None
    balanced = format_balanced(result)
    return (
        "[Verified stoichiometry]\n"
        f"Balanced equation: {balanced}\n"
        "Use mole ratios from the balanced coefficients. No numerical yield is verified "
        "because the question does not supply a complete amount and target pair."
    )


def _descriptor_block(smiles: str) -> str | None:
    try:
        desc = chemistry_service.compute_descriptors(smiles)
    except Exception:
        logger.info("descriptor context failed for %r", smiles, exc_info=True)
        return None
    if desc.error is not None:
        return None
    return (
        f"[Verified molecular descriptors for {desc.smiles}]\n"
        f"MW: {desc.molecular_weight} g/mol\n"
        f"LogP: {desc.log_p or 0.0}\n"
        f"TPSA: {desc.tpsa}\n"
        f"H-bond donors: {desc.h_bond_donors}\n"
        f"H-bond acceptors: {desc.h_bond_acceptors}\n"
        f"Rotatable bonds: {desc.rotatable_bonds}\n"
        f"Rings: {desc.ring_count}\n"
        "Use these values verbatim in your answer."
    )


def _smiles_candidates(content: str) -> list[str]:
    """Tokens that read as SMILES, in order; a plain word never qualifies."""
    tokens: list[str] = []
    for raw in content.split():
        token = raw.strip("?!,;'\"").rstrip(".")
        if _MIN_SMILES_TOKEN <= len(token) <= MAX_SMILES_LENGTH and _SMILES_TOKEN.match(token):
            tokens.append(token)
        if len(tokens) == _MAX_DESCRIPTOR_CANDIDATES:
            break
    return tokens


def _descriptor_context(content: str) -> str | None:
    if _DESCRIPTOR_CUE.search(content) is None:
        return None
    for smiles in _smiles_candidates(content):
        block = _descriptor_block(smiles)
        if block is not None:
            return block
    return None


def _named_elements(content: str) -> list[Element]:
    """Every element the question names, by whole word, atomic number, or asked-about symbol."""
    found: dict[int, Element] = {}
    words = list(_WORD.finditer(content))
    for index, match in enumerate(words):
        element = _ELEMENT_BY_NAME.get(match.group(0).lower())
        if element is None:
            continue
        if index + 1 < len(words):
            following = words[index + 1]
            between = content[match.end() : following.start()]
            if between.isspace() and following.group(0).lower() in _COMPOUND_FOLLOWERS:
                continue
        found.setdefault(element.number, element)
    for number in _ATOMIC_NUMBER.finditer(content):
        element = BY_NUMBER.get(int(number.group(1)))
        if element is not None:
            found.setdefault(element.number, element)
    for symbol in _SYMBOL_AFTER_CUE.finditer(content):
        element = _SYMBOL_BY_TEXT.get(symbol.group(1))
        if element is not None:
            found.setdefault(element.number, element)
    return list(found.values())[:_MAX_ELEMENTS]


def _element_block(element: Element) -> list[str]:
    lines = [f"[Verified element data for {element.name}]", f"Atomic mass: {element.mass} g/mol"]
    if element.group is not None:
        lines.append(f"Group: {element.group}")
    lines.append(f"Period: {element.period}")
    lines.append(f"Atomic number: {element.number}")
    lines.append(f"Electron configuration: {element.configuration}")
    if element.electronegativity is not None:
        lines.append(f"Electronegativity: {element.electronegativity}")
    if element.oxidation_states:
        states = ", ".join(f"{state:+d}" for state in element.oxidation_states)
        lines.append(f"Common oxidation states: {states}")
    if element.mass_is_isotope:
        lines.append("Mass note: mass number of a long-lived isotope")
    return lines


def _element_context(content: str) -> str | None:
    if _ELEMENT_CUE.search(content) is None:
        return None
    elements = _named_elements(content)
    if not elements:
        return None
    lines: list[str] = []
    for element in elements:
        if lines:
            lines.append("")
        lines.extend(_element_block(element))
    lines.append("Use these values verbatim in your answer.")
    return "\n".join(lines)


def unverified_chemistry_note() -> str:
    return (
        "Chemistry note: a chemistry calculation was detected, but no complete "
        "verified result is available. Do not claim verification or invent the "
        "missing value. Do not emit answer, smiles, or chem_scene fences.\n\n"
        f"For a calculation: {WORKOUT_PROMPT_RULE} {SELF_CHECK_PROMPT_RULE}"
    )


def append_unverified_chemistry_note(content: str) -> str:
    """Keep the chemistry decline in the prompt. Do not paste it under the answer."""
    note = unverified_chemistry_note()
    if note not in content:
        return content
    without = content.replace(f"\n\n{note}", "")
    without = without.replace(note, "")
    return without.rstrip()


def _solve_locally(
    content: str,
) -> tuple[ChemistryIntent | None, VerifiedChemistry | None, str | None]:
    """The CPU-bound part of a chemistry turn: read the question, solve it, or build
    local context (balancing, RDKit descriptors). Runs in the SymPy pool, where a
    pathological question is stopped at the solve timeout instead of holding the
    event loop and every other request on it."""
    intent = extract_chemistry_intent(content)
    if intent is not None:
        solved = build_verified_chemistry(intent)
        if solved is not None:
            return intent, solved, None
    for local_context in (
        _stoichiometry_ratio_hint(content),
        _descriptor_context(content),
        _element_context(content),
    ):
        if local_context is not None:
            return intent, None, local_context
    return intent, None, None


def _read_locally(
    content: str,
) -> tuple[ChemistryIntent | None, VerifiedChemistry | None, str | None, str | None]:
    """``_solve_locally``, and the compound to look up when nothing local answers. The gate
    is a pure reading of the text and is read here, in the pool, never on the event loop."""
    intent, solved, local_context = _solve_locally(content)
    lookup = None
    if intent is None and solved is None and local_context is None:
        lookup = extract_compound_name(content) if is_chemistry_question(content) else None
    return intent, solved, local_context, lookup


async def build_chemistry_augmentation(
    content: str,
    settings: Settings,
    redis: Redis | None = None,
) -> tuple[str | None, VerifiedChemistry | None, bool]:
    """Return prompt context, a typed solve, and whether that solve declined.

    The third value is true only when a verification was attempted and nothing
    verified replaced it. A PubChem record or element table is context, so it
    stays false.
    """
    content = read_chemistry_text(content)
    iupac_smiles = _iupac_smiles(content)
    if iupac_smiles is not None:
        try:
            name = await asyncio.wait_for(
                pubchem_gateway.lookup_iupac_name(iupac_smiles, redis=redis), PUBCHEM_BUDGET_SECONDS
            )
        except TimeoutError:
            logger.info("PubChem IUPAC lookup timed out")
            name = None
        if not name:
            return (
                "[Chemistry note]\n"
                "No verified IUPAC name was returned for that SMILES. "
                "Do not invent an IUPAC name.",
                None,
                True,
            )
        verified = verified_iupac(iupac_smiles, name)
        return verified.prompt_text, verified, False
    try:
        intent, solved, local_context, name = await run_sympy(
            _read_locally, content, timeout=settings.stem_solve_timeout_seconds
        )
    except TimeoutError:
        logger.warning("chemistry solve timed out after %ss", settings.stem_solve_timeout_seconds)
        return unverified_chemistry_note(), None, True
    except Exception:
        logger.warning("chemistry solve failed", exc_info=True)
        return unverified_chemistry_note(), None, True
    if solved is not None:
        answer = solved.result.answer
        if asks_more_parts(content, answer) or asks_more_particles(content, answer):
            return f"{solved.prompt_text}\n{ONE_PART_NOTE}", solved, False
        return solved.prompt_text, solved, False
    if local_context is not None:
        return local_context, None, False

    if intent is not None:
        return unverified_chemistry_note(), None, True
    if name is None:
        return None, None, False
    try:
        lookup = await asyncio.wait_for(
            pubchem_gateway.lookup_by_name(name, redis=redis), PUBCHEM_BUDGET_SECONDS
        )
    except TimeoutError:
        logger.info("PubChem lookup timed out for %r", name)
        return unverified_chemistry_note(), None, True
    if lookup.error is not None or lookup.compound is None:
        logger.info("PubChem lookup failed for %r: %s", name, lookup.error)
        return unverified_chemistry_note(), None, True
    compound = lookup.compound
    if _SEE_STRUCTURE.search(content):
        verified = verified_structure(
            name, compound.smiles, compound.molecular_formula, compound.molecular_weight
        )
        return verified.prompt_text, verified, False
    lines = [
        f"[Chemistry context for {name}]",
        f"Canonical SMILES: {compound.smiles}",
        f"Molecular formula: {compound.molecular_formula}",
        f"Molecular weight: {compound.molecular_weight:.2f} g/mol",
        f"PubChem CID: {compound.cid}",
        "Use the SMILES above verbatim in a ```smiles fence if you show the structure.",
    ]
    if _DESCRIPTOR_CUE.search(content) is not None:
        descriptors = _descriptor_block(compound.smiles)
        if descriptors is not None:
            lines.extend(["", descriptors])
    return "\n".join(lines), None, False


def _iupac_smiles(content: str) -> str | None:
    match = _IUPAC_SMILES.search(content)
    if match is None:
        return None
    token = match.group(1).rstrip("?.!,")
    return token or None


__all__ = [
    "build_chemistry_augmentation",
    "extract_compound_name",
    "is_chemistry_question",
]
