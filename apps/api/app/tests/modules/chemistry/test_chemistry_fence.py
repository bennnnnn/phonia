"""Chemistry fence enrichment — validate/enrich ```smiles fences."""

from __future__ import annotations

import pytest

from app.modules.chemistry import fence as chemistry_fence
from app.modules.chemistry.reply_policy import CHEMISTRY_FENCE_HINT


def test_enrich_valid_smiles_canonicalizes() -> None:
    content = "```smiles\nOCC\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    # OCC and CCO are both ethanol — should canonicalize to the same form.
    assert "```smiles" in result
    # Should not contain the original OCC
    assert "OCC" not in result


@pytest.mark.parametrize(
    ("written", "drawn"),
    [
        # PubChem's caffeine: ring carbons with =O and aromatic N drew as CH₂ and HC.
        ("Cn1c(=O)c2c(ncn2C)n(C)c1=O", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"),
        ("c1ccncc1", "C1=CC=NC=C1"),
        ("c1ccccc1", "C1=CC=CC=C1"),
        ("c1cc[nH]c1", "C1=CNC=C1"),
        ("CCO", "CCO"),
    ],
)
def test_enrich_writes_the_kekule_smiles_the_phone_draws(written: str, drawn: str) -> None:
    # smiles-drawer counts an aromatic bond as single when it adds hydrogens.
    result = chemistry_fence.enrich_chemistry_fences(f"```smiles\n{written}\n```")
    assert f"\n{drawn}\n```" in result


def test_enrich_valid_smiles_with_caption() -> None:
    content = "```smiles\nEthanol\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" in result
    assert "Ethanol" in result  # caption preserved


def test_enrich_invalid_smiles_stripped() -> None:
    content = "Here is a molecule:\n```smiles\nnot_a_smiles\n```\nDone."
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" not in result
    assert "not_a_smiles" not in result
    assert "Done." in result


def test_enrich_multiple_smiles_fences() -> None:
    content = "```smiles\nCCO\n```\nand\n```smiles\nO=C=O\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert result.count("```smiles") == 2


def test_enrich_chemistry_alias_fence() -> None:
    content = "```chemistry\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    # Should be normalized to ```smiles
    assert "```smiles" in result
    assert CHEMISTRY_FENCE_HINT not in result


def test_enrich_no_smiles_fences_unchanged() -> None:
    content = "Just some text without chemistry fences."
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert result == content


def test_enrich_empty_fence_left_as_is() -> None:
    content = "```smiles\n\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    # Empty fence body — no SMILES to validate. A trailing newline after the
    # closer is ok (keeps the next fence from gluing onto the closer).
    assert result.count("```smiles") == 1
    assert "Could not render" not in result


def test_enrich_smiles_with_comment_lines() -> None:
    content = "```smiles\n# This is ethanol\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" in result


def test_enrich_diatomic_formula_h2_keeps_smiles_and_3d() -> None:
    """`H2` is a formula, not SMILES — still emit 2D + 3D like O=O."""
    content = "```smiles\nH2\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" in result
    assert "[H][H]" in result
    assert "```molecule3d" in result
    assert "M  END" in result


def test_enrich_generates_molecule3d_fence() -> None:
    """Valid SMILES should also produce a ```molecule3d fence with 3D SDF."""
    content = "```smiles\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" in result
    assert "```molecule3d" in result
    assert "M  END" in result  # SDF block present


def test_enrich_molecule3d_includes_formula_title() -> None:
    """The molecule3d fence should include the molecular formula as title."""
    content = "```smiles\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```molecule3d" in result
    # Ethanol formula is C2H6O — after M END, never as an extra header line.
    assert "C2H6O" in result
    mol3d = result.split("```molecule3d", 1)[1].split("```", 1)[0]
    end = mol3d.index("M  END")
    assert "C2H6O" in mol3d[end:]
    assert mol3d.strip().splitlines()[0].strip() != "C2H6O"


def test_enrich_surfaces_verified_properties_in_caption() -> None:
    """When no caption is provided, the fence should include formula + MW as caption."""
    content = "```smiles\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    # Ethanol: C2H6O, MW ~46.07
    assert "C2H6O" in result
    assert "g/mol" in result


def test_enrich_chemistry_fences_worker_passthrough() -> None:
    """The worker function (called from stream.py process pool) should match the main function."""
    content = "```smiles\nCCO\n```"
    result = chemistry_fence.enrich_chemistry_fences_worker(content)
    assert "```smiles" in result
    assert "```molecule3d" in result


def test_enrich_multiple_fences_all_get_3d() -> None:
    """Two valid SMILES fences should each get a molecule3d fence."""
    content = "```smiles\nCCO\n```\n\nSome text.\n\n```smiles\nO=O\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert result.count("```molecule3d") == 2


def test_enrich_unclosed_smiles_does_not_swallow_python() -> None:
    content = "```smiles\nCCO\n```python\nprint(1)\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```python" in result
    assert "print(1)" in result


def test_enrich_smiles_then_caption_still_validates() -> None:
    content = "```smiles\nCCO\nethanol\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert "```smiles" in result
    assert "Could not render" not in result
    assert "ethanol" in result


def test_enrich_third_molecule_skips_3d() -> None:
    content = "```smiles\nCCO\n```\n```smiles\nO=O\n```\n```smiles\nO=C=O\n```"
    result = chemistry_fence.enrich_chemistry_fences(content)
    assert result.count("```smiles") == 3
    assert result.count("```molecule3d") == 2


def test_enrich_accepts_a_smiles_prefix_in_any_case() -> None:
    result = chemistry_fence.enrich_chemistry_fences("```smiles\nSMILES: CCO\n```")
    assert "Could not render" not in result
    assert "SMILES:" not in result
    assert "CCO" in result


@pytest.mark.parametrize(
    ("formula", "canonical"),
    [
        ("H2O", "O"),
        ("CO2", "O=C=O"),
        ("NH3", "N"),
        ("CH4", "C"),
        ("HCl", "Cl"),
        ("NaCl", "[Cl-].[Na+]"),
    ],
)
def test_enrich_reads_a_formula_the_model_wrote_in_place_of_smiles(
    formula: str, canonical: str
) -> None:
    result = chemistry_fence.enrich_chemistry_fences(f"```smiles\n{formula}\n```")
    assert "Could not render" not in result
    assert f"\n{canonical}\n```" in result


def test_validate_chemistry_fences_closes_an_open_model_fence_before_appending() -> None:
    from app.modules.chemistry.block import build_verified_chemistry
    from app.modules.chemistry.extract import extract_chemistry_intent

    intent = extract_chemistry_intent("Find the molar mass of H2SO4")
    assert intent is not None
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = chemistry_fence.validate_chemistry_fences("Sure:\n```smiles\nCCO", verified=verified)
    assert reply.count("```") % 2 == 0
    assert "CCO" not in reply
    assert "```answer" in reply
