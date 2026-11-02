"""Chemistry context — PubChem turn_prep injection and intent detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.modules.chemistry import context as chemistry_context

_SETTINGS = Settings()

# ---------------------------------------------------------------------------
# is_chemistry_question
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what is the structure of aspirin?", True),
        ("draw the molecule caffeine", True),
        ("Draw the structure of carbon dioxide.", True),
        ("molecular formula of ethanol", True),
        ("what is the SMILES for glucose", True),
        ("tell me about water as a compound", True),
        ("balance the equation H2 + O2 -> H2O", True),
        ("Balance H2 + O2 -> H2O", True),
        ("Molar mass of C6H12O6", True),
        ("Calculate the molar mass of H2SO4", True),
        ("What is the pH when [H+] = 0.001?", True),
        ("Calculate the molarity of 0.5 mol in 2 L", True),
        ("A gas at 2 atm and 300 K occupies what volume? PV=nRT", True),
        ("How many moles of H2O from 4 mol H2 in H2 + O2 -> H2O?", True),
        ("What is the LogP of CC(=O)OC1=CC=CC=C1C(=O)O?", True),
        ("Solve the chemistry problem in this image step by step.", True),
        ("how many days until the trip", False),
        ("what is 2 + 2?", False),
        ("What is the capital of France?", False),
        ("", False),
    ],
)
def test_is_chemistry_question(text: str, expected: bool) -> None:
    assert chemistry_context.is_chemistry_question(text) is expected


# ---------------------------------------------------------------------------
# extract_compound_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what is aspirin?", "aspirin"),
        ("structure of caffeine", "caffeine"),
        ("molecular formula of ethanol", "ethanol"),
        ("draw the molecule glucose", "glucose"),
        ("Draw the structure of carbon dioxide.", "carbon dioxide"),
        ("show the lewis structure of carbon dioxide", "carbon dioxide"),
        ("what is 2 + 2?", None),
        ("", None),
    ],
)
def test_extract_compound_name(text: str, expected: str | None) -> None:
    assert chemistry_context.extract_compound_name(text) == expected


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — PubChem lookup
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_pubchem_success() -> None:
    """When PubChem returns a compound, the context block includes SMILES + formula."""
    fake_compound = MagicMock()
    fake_compound.smiles = "CC(=O)Oc1ccccc1C(=O)O"
    fake_compound.molecular_formula = "C9H8O4"
    fake_compound.molecular_weight = 180.16
    fake_compound.cid = 2244
    fake_result = MagicMock()
    fake_result.error = None
    fake_result.compound = fake_compound

    with patch.object(
        chemistry_context.pubchem_gateway, "lookup_by_name", new_callable=AsyncMock
    ) as mock_lookup:
        mock_lookup.return_value = fake_result
        block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
            "what is aspirin?", _SETTINGS
        )
    assert block is not None
    assert "Canonical SMILES: CC(=O)Oc1ccccc1C(=O)O" in block
    assert "Molecular formula: C9H8O4" in block
    assert "PubChem CID: 2244" in block


async def test_build_chemistry_augmentation_does_not_teach_molecule3d() -> None:
    """PubChem 3D SDF in the prompt taught a second ```molecule3d fence on top
    of the server-appended one — two molecule cards, one of them empty."""
    fake_compound = MagicMock()
    fake_compound.smiles = "CCO"
    fake_compound.molecular_formula = "C2H6O"
    fake_compound.molecular_weight = 46.07
    fake_compound.cid = 702
    fake_result = MagicMock()
    fake_result.error = None
    fake_result.compound = fake_compound

    with patch.object(
        chemistry_context.pubchem_gateway,
        "lookup_by_name",
        new_callable=AsyncMock,
    ) as mock_lookup:
        mock_lookup.return_value = fake_result
        block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
            "Show the molecular structure of ethanol. Include 2D and 3D.",
            _SETTINGS,
        )
    assert block is not None
    assert "molecule3d" not in block
    assert "3D SDF" not in block


async def test_build_chemistry_augmentation_pubchem_not_found() -> None:
    """A named lookup that errors declines with the chemistry note."""
    fake_result = MagicMock()
    fake_result.error = "not found"
    fake_result.compound = None

    with patch.object(
        chemistry_context.pubchem_gateway, "lookup_by_name", new_callable=AsyncMock
    ) as mock_lookup:
        mock_lookup.return_value = fake_result
        block, _verified, declined = await chemistry_context.build_chemistry_augmentation(
            "structure of caffeine", _SETTINGS
        )
    assert declined is True
    assert block == chemistry_context.unverified_chemistry_note()


async def test_build_chemistry_augmentation_non_chemistry() -> None:
    """Non-chemistry questions return None."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is 2 + 2?", _SETTINGS
    )
    assert block is None


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — equation balancing
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_balance_equation() -> None:
    """When the user asks to balance an equation, the context block includes the balanced form."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "balance the equation H2 + O2 -> H2O", _SETTINGS
    )
    assert block is not None
    assert "Verified balanced equation" in block
    assert "2 H2" in block or "2  H2" in block
    assert "2 H2O" in block or "2  H2O" in block


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — molar mass
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_molar_mass() -> None:
    """When the user asks for molar mass, the context block includes the verified mass."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is the molar mass of H2O?", _SETTINGS
    )
    assert block is not None
    assert "Verified molar mass" in block
    assert "18" in block


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — stoichiometry
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_stoichiometry() -> None:
    """When the user asks 'how much product' with an equation, stoichiometry context is injected."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "how much H2O is produced from H2 + O2 -> H2O?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified stoichiometry" in block
    assert "Balanced equation" in block


async def test_build_chemistry_augmentation_stoichiometry_with_amount() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "How many moles of H2O from 4 mol H2 in H2 + O2 -> H2O?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified stoichiometry" in block
    assert "mol H2" in block
    assert "H2O" in block


async def test_build_chemistry_augmentation_limiting_reagent() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "limiting reagent: 1 mol H2 and 1 mol O2 in H2 + O2 -> H2O",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified limiting reagent" in block
    assert "H2" in block


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — pH
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_ph() -> None:
    """When the user asks about pH with [H+], the verified pH is injected."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is the pH if [H+] = 0.001?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified pH calculation" in block
    # 0.001 has one significant figure, raised to the two-figure floor: two decimals.
    assert "pH = 3.00" in block


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — gas law
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_gas_law() -> None:
    """Gas-law questions without enough numbers do not fake a verified block."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "use PV=nRT to find the pressure of an ideal gas",
        _SETTINGS,
    )
    assert block is None


async def test_build_chemistry_augmentation_gas_law_does_not_steal_pubchem() -> None:
    fake_compound = MagicMock()
    fake_compound.smiles = "CC(=O)Oc1ccccc1C(=O)O"
    fake_compound.molecular_formula = "C9H8O4"
    fake_compound.molecular_weight = 180.16
    fake_compound.cid = 2244
    fake_result = MagicMock()
    fake_result.error = None
    fake_result.compound = fake_compound
    with patch.object(
        chemistry_context.pubchem_gateway, "lookup_by_name", new_callable=AsyncMock
    ) as mock_lookup:
        mock_lookup.return_value = fake_result
        block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
            "what is aspirin? the pressure and volume of the bottle are unknown",
            _SETTINGS,
        )
    assert block is not None
    assert "Canonical SMILES" in block
    assert "Verified gas law" not in block
    mock_lookup.assert_awaited()


# ---------------------------------------------------------------------------
# build_chemistry_augmentation — solution chemistry
# ---------------------------------------------------------------------------


async def test_build_chemistry_augmentation_solution() -> None:
    """Molarity without numbers does not fake a verified block."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "calculate the molarity of the solution",
        _SETTINGS,
    )
    assert block is None


async def test_build_chemistry_augmentation_molarity_verified() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "Calculate the molarity of 0.5 mol in 2 L",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified molarity" in block
    assert "0.2500" in block or "0.25" in block


async def test_build_chemistry_augmentation_poh() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is the pH when pOH = 4?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified pH calculation" in block
    assert "10.00" in block or "10" in block


async def test_build_chemistry_augmentation_element() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is the atomic mass of Fe?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified element data" in block
    assert "55.845" in block
    assert "Atomic number: 26" in block
    assert "Electron configuration:" in block
    assert "Verified molar mass" not in block


async def test_build_chemistry_augmentation_h_from_ph() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "what is [H+] when pH = 3?",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified pH calculation" in block
    assert "e-03" in block or "0.001" in block


async def test_build_chemistry_augmentation_dilution() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "dilute a solution: M1=2 V1=1 M2=1",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified dilution" in block
    assert "2.0000" in block or "2" in block


async def test_build_chemistry_augmentation_stoich_named_product_not_first_rhs() -> None:
    """'how much H2O' must not verify CO2 just because it appears first in the equation."""
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "how much H2O from 2 mol C2H6 in C2H6 + O2 -> CO2 + H2O",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified stoichiometry" in block
    assert "H2O" in block
    assert "mol CO2" not in block


async def test_build_chemistry_augmentation_element_as_is_not_arsenic() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "Which element is used as a semiconductor?",
        _SETTINGS,
    )
    assert block is None or "Arsenic" not in block
    if block is not None:
        assert "Verified element data" not in block


async def test_build_chemistry_augmentation_dilution_ml_keeps_ml() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "dilute a solution: M1=1 V1=100 mL M2=0.5",
        _SETTINGS,
    )
    assert block is not None
    assert "Verified dilution" in block
    assert "200" in block
    assert "mL" in block
    assert "200.0000 L" not in block
    assert "100.0000 L" not in block


async def test_build_chemistry_augmentation_gas_law_zero_pressure_does_not_crash() -> None:
    block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
        "PV=nRT find the volume of 1 mol at 0 atm and 273 K",
        _SETTINGS,
    )
    assert block is None or "Verified gas law" not in block


@pytest.mark.parametrize(
    ("question", "names"),
    [
        ("What is the atomic number of gold?", ["Gold"]),
        ("Tell me the electronegativity of caesium", ["Cesium"]),
        ("What is the atomic mass of aluminium and sulphur?", ["Aluminum", "Sulfur"]),
        ("What are the atomic masses of sodium and chlorine?", ["Sodium", "Chlorine"]),
        ("Which element has atomic number 79?", ["Gold"]),
        ("electron configuration of Fe", ["Iron"]),
        ("what is the electronegativity of Cs?", ["Cesium"]),
    ],
)
def test_element_context_names_every_element_asked_about(question: str, names: list[str]) -> None:
    block = chemistry_context._element_context(question)
    assert block is not None
    for name in names:
        assert f"[Verified element data for {name}]" in block
    assert block.count("[Verified element data for") == len(names)


@pytest.mark.parametrize(
    "question",
    [
        "What is the atomic mass of carbon dioxide?",
        "atomic mass of sodium chloride",
        "atomic mass of H2O",
        "In group 1, which element has the highest electronegativity?",
        "As a student, which element should I study first?",
        "Which element is used as a semiconductor?",
        "the hydrogen bond is an element of surprise",
    ],
)
def test_element_context_ignores_compounds_and_stray_capitals(question: str) -> None:
    assert chemistry_context._element_context(question) is None


def test_element_context_prints_oxidation_states_and_configuration() -> None:
    block = chemistry_context._element_context("oxidation states of Mn")
    assert block is not None
    assert "Common oxidation states: +2, +4, +7" in block
    assert "Electron configuration: [Ar] 3d5 4s2" in block


@pytest.mark.parametrize(
    ("question", "smiles"),
    [
        ("Calculate the logP of CCO please", "CCO"),
        ("What is the LogP of CC(=O)OC1=CC=CC=C1C(=O)O?", "CC(=O)Oc1ccccc1C(=O)O"),
        ("Lipinski check for CC(C)Cc1ccc(cc1)C(C)C(=O)O.", "CC(C)Cc1ccc(C(C)C(=O)O)cc1"),
    ],
)
def test_descriptor_context_finds_the_smiles_not_the_first_capitalised_word(
    question: str, smiles: str
) -> None:
    block = chemistry_context._descriptor_context(question)
    assert block is not None
    assert f"[Verified molecular descriptors for {smiles}]" in block


def test_descriptor_context_has_nothing_to_read_in_a_plain_sentence() -> None:
    assert chemistry_context._descriptor_context("Calculate the logP for this drug") is None
    assert "LogP: 0.0" in (chemistry_context._descriptor_context("logP of CCO") or "")


async def test_logp_of_a_named_compound_uses_the_pubchem_smiles() -> None:
    compound = MagicMock()
    compound.smiles = "CC(=O)Oc1ccccc1C(=O)O"
    compound.molecular_formula = "C9H8O4"
    compound.molecular_weight = 180.16
    compound.cid = 2244
    result = MagicMock()
    result.error = None
    result.compound = compound
    with patch.object(
        chemistry_context.pubchem_gateway, "lookup_by_name", new_callable=AsyncMock
    ) as mock_lookup:
        mock_lookup.return_value = result
        block, _verified, _declined = await chemistry_context.build_chemistry_augmentation(
            "logP of aspirin", _SETTINGS
        )
    assert block is not None
    assert "Canonical SMILES: CC(=O)Oc1ccccc1C(=O)O" in block
    assert "LogP: 1.31" in block
