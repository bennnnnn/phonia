"""Chemistry prompt hints: how a chemistry answer is presented, and how its structures are
fenced."""

CHEMISTRY_PRESENTATION_HINT = (
    "This is a chemistry answer. Keep species, amounts, and units easy to scan. "
    "Write species with Unicode sub- and superscripts (H₂O, Fe³⁺, SO₄²⁻), reactions with → "
    "or ⇌, and never put a bare species or unit in LaTeX. "
    "When you calculate, follow the calculation layout: one reasoning state per row."
)


def chemistry_prompt_hints(short: bool) -> tuple[str, ...]:
    """The chemistry pack. Short style and a compact turn get the same one."""
    return (CHEMISTRY_PRESENTATION_HINT,)


CHEMISTRY_FENCE_HINT = (
    "This turn is chemistry. Molecular structures: ```smiles (alias ```chemistry) "
    "with a plain SMILES string — never geometry, graph, mermaid, HTML/SVG, "
    "`$...$`, or ```math. One molecule per fence; optional caption above the SMILES. "
    "Use verified SMILES from the system block verbatim when present. "
    "Do not emit ```molecule3d; do not mention attaching or 3D fences. "
    "Do not add 2D/3D section headings around the structure. "
    "Do not emit a molecule card unless this turn is actually about a chemical structure."
)


def attach_chemistry_fence_hint(block: str) -> str:
    """Teach ```smiles only when this turn actually has a verified structure."""
    if "Canonical SMILES" in block or "Verified molecular descriptors" in block:
        return f"{CHEMISTRY_FENCE_HINT}\n\n{block}"
    return block
