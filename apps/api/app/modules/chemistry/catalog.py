# ruff: noqa: RUF001 -- textbook formulas use minus signs and multiplication signs.
"""One FormulaSpec per chemistry operation.

The catalog is the identity of each operation: the law's name and its formula exactly as an
answer prints them, and the one list of operations: ``ChemistryIntent`` refuses an operation
the catalog does not declare. Solvers keep region-specific working, such as a titration
before or after equivalence. Tests fail when the catalog drifts from the solver map or from
what a solver prints.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.chemistry.formula_laws import FORMULA_LAWS


@dataclass(frozen=True, slots=True)
class FormulaSpec:
    id: str
    kind: str
    law_name: str
    base_formula: str
    # A procedure, not an equation: the answer shows it under **Method** as a rule.
    method: bool = False


# Operations answered by a procedure (balancing, a table lookup, a structure match).
METHODS = frozenset(
    {
        "balance",
        "half_reaction",
        "precipitation",
        "functional_groups",
        "stereochemistry",
        "isomers",
        "iupac_name",
        "structure",
        "named_reaction",
        "ir_ranges",
        "ir_peak",
        "nmr_ranges",
        "nmr_peak",
        "molecular_ion",
        "electron_configuration",
        "valence_electrons",
        "ionic_formula",
        "ionic_name",
    }
)


def _spec(operation: str, kind: str, law_name: str, base_formula: str) -> FormulaSpec:
    return FormulaSpec(operation, kind, law_name, base_formula, operation in METHODS)


_ROWS: tuple[tuple[str, str, str, str], ...] = (
    (
        "balance",
        "equations",
        "Conservation of atoms and charge",
        "count each element's atoms on both sides; the smallest whole-number coefficients that "
        "make every count, and the charge, equal",
    ),
    (
        "half_reaction",
        "equations",
        "Half-reaction method",
        "balance the redox pair, add H2O for oxygen, add H+ or OH- for the stated medium, "
        "then add e- to balance the charge",
    ),
    ("molar_mass", "amounts", "Molar mass from atomic masses", "M = Σ(nᵢ × atomic massᵢ)"),
    ("mass_to_moles", "amounts", "Mass–mole relation", "n = m / M"),
    ("moles_to_mass", "amounts", "Mass–mole relation", "m = nM"),
    ("moles_to_particles", "amounts", "Avogadro relation", "N = nNₐ"),
    ("particles_to_moles", "amounts", "Avogadro relation", "n = N / Nₐ"),
    ("mass_to_particles", "amounts", "Avogadro relation", "N = (m / M)Nₐ"),
    (
        "percent_composition",
        "amounts",
        "Percent composition",
        "% element = (mass of element in 1 mol compound / molar mass) × 100",
    ),
    (
        "percent_yield",
        "amounts",
        "Percent yield formula",
        "% yield = (actual yield / theoretical yield) × 100",
    ),
    (
        "atom_economy",
        "amounts",
        "Atom economy",
        "% atom economy = ν M(desired) / Σ ν M(reactants) × 100",
    ),
    (
        "stoichiometry",
        "stoichiometry",
        "Stoichiometric mole ratio",
        "n(product) = n(reactant) × (product coefficient / reactant coefficient)",
    ),
    (
        "limiting_reagent",
        "stoichiometry",
        "Stoichiometric limiting-reagent comparison",
        "reaction units = available moles / stoichiometric coefficient",
    ),
    ("molarity", "solutions", "Molar concentration", "c = n / V"),
    ("dilution", "solutions", "Dilution equation", "M1V1 = M2V2"),
    ("molality", "solutions", "Molality formula", "b = moles of solute / kilograms of solvent"),
    (
        "mass_percent",
        "solutions",
        "Mass-percent concentration",
        "mass % = (mass of solute / mass of solution) × 100",
    ),
    ("ph_from_h", "acid_base", "Definition of pH", "pH = −log10[H+]"),
    ("ph_from_poh", "acid_base", "Water ion-product relation", "pH + pOH = 14"),
    ("h_from_ph", "acid_base", "Inverse pH relation", "[H+] = 10^(-pH)"),
    ("poh_from_oh", "acid_base", "Definition of pOH", "pOH = −log10[OH-]"),
    ("buffer_ph", "acid_base", "Henderson–Hasselbalch equation", "pH = pKa + log10([A-]/[HA])"),
    ("base_buffer_ph", "acid_base", "Base-buffer pH", "pH = pKw − pKb − log10([BH+]/[B])"),
    ("strong_acid_poh", "acid_base", "Strong-acid pOH", "pOH = pKw + log10(C)"),
    ("strong_base_poh", "acid_base", "Strong-base pOH", "pOH = −log10(nC)"),
    ("weak_acid_ka", "acid_base", "Weak-acid constant", "Ka = x^2 / (C − x)"),
    ("conjugate_salt_ph", "acid_base", "Hydrolysis of a conjugate salt", "Kb = Kw / Ka"),
    ("gibbs", "thermochemistry", "Gibbs equation", "ΔG = ΔH − TΔS"),
    (
        "equilibrium_constant",
        "equilibrium",
        "Law of mass action",
        "Kc = Π [products]^ν / Π [reactants]^ν",
    ),
    (
        "reaction_quotient",
        "equilibrium",
        "Law of mass action",
        "Qc = Π [products]^ν / Π [reactants]^ν",
    ),
    ("first_order_half_life", "kinetics", "First-order half-life", "t₁/₂ = ln(2) / k"),
    (
        "first_order_concentration",
        "kinetics",
        "Integrated first-order rate law",
        "[A]ₜ = [A]₀e^(−kt)",
    ),
    ("first_order_time", "kinetics", "Integrated first-order rate law", "t = ln([A]₀/[A]ₜ) / k"),
    ("arrhenius", "kinetics", "Arrhenius equation", "k = Ae^(−Eₐ/(RT))"),
    ("cell_gibbs", "electrochemistry", "Electrochemical Gibbs relation", "ΔG° = −nFE°cell"),
    ("nernst", "electrochemistry", "Nernst equation", "E = E° − (RT/nF)ln Q"),
    ("galvanic_nernst", "electrochemistry", "Nernst equation", "E = E° − (RT/nF)ln Q"),
    ("electrolysis_mass", "electrochemistry", "Faraday's law of electrolysis", "m = MIt / nF"),
    ("beer_lambert", "spectroscopy", "Beer–Lambert law", "A = εbc"),
    (
        "empirical_formula",
        "amounts",
        "Empirical formula from percent composition",
        "n = (percent / atomic mass) / smallest",
    ),
    (
        "combustion_analysis",
        "amounts",
        "Combustion analysis",
        "n(C) = m(CO2) / M(CO2); n(H) = 2 m(H2O) / M(H2O); m(O) = m(sample) − m(C) − m(H)",
    ),
    (
        "hydrate_water",
        "amounts",
        "Hydrate water coefficient",
        "n = (m(hydrate) − m(salt)) / M(H2O) × M(salt) / m(salt)",
    ),
    (
        "molecular_formula",
        "amounts",
        "Molecular formula from the empirical formula",
        "n = M_molecular / M_empirical",
    ),
    (
        "mass_stoichiometry",
        "stoichiometry",
        "Mass–mole–particle stoichiometry",
        "n(product) = n(reactant) × (product coefficient / reactant coefficient)",
    ),
    (
        "solution_stoichiometry",
        "stoichiometry",
        "Mass–mole–particle stoichiometry",
        "n(product) = n(reactant) × (product coefficient / reactant coefficient)",
    ),
    (
        "gas_stoichiometry",
        "stoichiometry",
        "Mass–mole–particle stoichiometry",
        "n(product) = n(reactant) × (product coefficient / reactant coefficient)",
    ),
    (
        "limiting_mass",
        "stoichiometry",
        "Limiting reagent from amounts",
        "reaction units = available moles / coefficient",
    ),
    (
        "reaction_percent_yield",
        "stoichiometry",
        "Percent yield from a reaction",
        "% yield = (actual yield / theoretical yield) × 100",
    ),
    (
        "limiting_solution",
        "stoichiometry",
        "Limiting reagent from amounts",
        "reaction units = available moles / coefficient",
    ),
    ("strong_acid_ph", "acid_base", "Strong monoprotic acid", "[H+] = C"),
    ("strong_base_ph", "acid_base", "Strong base", "[OH-] = nC"),
    ("weak_acid_ph", "acid_base", "Weak-acid quadratic", "Ka = x^2 / (C − x)"),
    ("weak_base_ph", "acid_base", "Weak-base quadratic", "Kb = x^2 / (C − x)"),
    ("ka_kb", "acid_base", "Water autoionization link", "Kb = Kw / Ka"),
    (
        "titration_strong",
        "acid_base",
        "Strong acid–strong base titration",
        "[H+] = (n(H+) − n(OH-)) / (Va + Vb)",
    ),
    ("titration_weak", "acid_base", "Weak acid–strong base titration", "pH = pKa"),
    (
        "buffer_addition",
        "acid_base",
        "Henderson–Hasselbalch after addition",
        "pH = pKa + log10([A-]/[HA])",
    ),
    (
        "polyprotic_ph",
        "acid_base",
        "First dissociation of a polyprotic acid",
        "Ka1 = x^2 / (C − x)",
    ),
    (
        "amphiprotic_ph",
        "acid_base",
        "Amphiprotic approximation",
        "pH = (pKa1 + pKa2) / 2",
    ),
    (
        "diprotic_a2",
        "acid_base",
        "Second dissociation approximation",
        "[A2-] = Ka2",
    ),
    ("dalton", "gases", "Dalton's law", "Ptotal = Σ Pi"),
    ("partial_pressure", "gases", "Mole fraction", "Pi = Xi Ptotal"),
    ("gas_over_water", "gases", "Dalton's law with water vapor", "Pdry = Ptotal − Pwater"),
    ("graham", "gases", "Graham's law", "rate1 / rate2 = √(M2 / M1)"),
    ("calorimetry", "thermochemistry", "Calorimetry", "q_rxn = −Ccal ΔT"),
    ("hess", "thermochemistry", "Hess's law", "ΔH = Σ mi ΔHi"),
    (
        "formation_enthalpy",
        "thermochemistry",
        "Formation enthalpies",
        "ΔH°rxn = Σ n ΔHf°(products) − Σ n ΔHf°(reactants)",
    ),
    ("bond_enthalpy", "thermochemistry", "Bond enthalpies", "ΔH ≈ Σ broken − Σ formed"),
    (
        "clausius_clapeyron",
        "thermochemistry",
        "Clausius-Clapeyron equation",
        "ln(P2 / P1) = −ΔHvap / R × (1/T2 − 1/T1)",
    ),
    ("ksp", "equilibrium", "Solubility product", "Ksp = Π (νᵢ s)^νᵢ"),
    (
        "precipitation",
        "equilibrium",
        "Ion product versus solubility product",
        "compare Qsp with Ksp: above it a precipitate forms, below it none does, "
        "and equal is saturated",
    ),
    ("common_ion", "equilibrium", "Common-ion effect", "Ksp = Π [ion]^ν"),
    (
        "kp",
        "equilibrium",
        "Partial-pressure equilibrium constant",
        "Kp = Π P(products)^ν / Π P(reactants)^ν",
    ),
    ("kc_kp", "equilibrium", "Concentration and pressure equilibrium constants", "Kp = Kc (RT)^Δn"),
    (
        "ice_equilibrium",
        "equilibrium",
        "ICE table, quadratic or linear",
        "K = Π (initial + νx)^ν / Π (initial − νx)^ν",
    ),
    ("zero_order", "kinetics", "Integrated zero-order rate law", "[A]ₜ = [A]₀ − kt"),
    ("second_order", "kinetics", "Integrated second-order rate law", "1/[A]ₜ = 1/[A]₀ + kt"),
    ("zero_order_half_life", "kinetics", "Zero-order half-life", "t₁/₂ = [A]₀ / (2k)"),
    ("second_order_half_life", "kinetics", "Second-order half-life", "t₁/₂ = 1 / (k[A]₀)"),
    (
        "rate_law",
        "kinetics",
        "Order from two experiments",
        "order = log(rate2/rate1) / log(conc2/conc1)",
    ),
    (
        "arrhenius_two_point",
        "kinetics",
        "Two-point Arrhenius equation",
        "ln(k2/k1) = −(Ea/R)(1/T2 − 1/T1)",
    ),
    (
        "cell_potential",
        "electrochemistry",
        "Galvanic cell potential",
        "E°cell = E°cathode − E°anode",
    ),
    (
        "galvanic_cell",
        "electrochemistry",
        "Standard reduction potentials",
        "E°cell = E°cathode − E°anode",
    ),
    (
        "nuclear_equation",
        "nuclear",
        "Nucleon and charge balance",
        "ΣA(reactants) = ΣA(products) and ΣZ(reactants) = ΣZ(products)",
    ),
    (
        "oxidation_state",
        "structure",
        "School oxidation-number rules",
        "Σ (oxidation number × atoms) = charge",
    ),
    (
        "vsepr",
        "structure",
        "VSEPR from the central-atom Lewis structure",
        "steric number = bonded atoms + lone pairs",
    ),
    ("formal_charge", "structure", "Formal charge", "FC = V − N − B/2"),
    ("atom_particles", "structure", "Atomic structure", "A = Z + N; electrons = Z − charge"),
    (
        "valence_electrons",
        "structure",
        "Valence electrons from the group",
        "a main-group atom has its group number of valence electrons in groups 1 and 2 and "
        "the group number minus 10 in groups 13 to 18 (helium 2); a formula adds every atom's "
        "and takes away its charge",
    ),
    (
        "functional_groups",
        "organic",
        "Functional-group patterns",
        "match each group's SMARTS pattern against the molecule atom by atom (RDKit)",
    ),
    (
        "stereochemistry",
        "organic",
        "Cahn–Ingold–Prelog priorities",
        "rank each stereocenter's substituents for R/S and each double bond's for E/Z (RDKit)",
    ),
    (
        "isomers",
        "organic",
        "Formula and canonical structure",
        "compare the molecular formulas, then the canonical SMILES with and without "
        "stereochemistry: identical, constitutional isomers or stereoisomers",
    ),
    (
        "ionic_formula",
        "inorganic",
        "Ionic formula from ion charges",
        "write the fewest cations and anions whose charges sum to zero, cation first, a "
        "polyatomic ion in brackets when there is more than one",
    ),
    (
        "ionic_name",
        "inorganic",
        "Ionic name from ion charges",
        "name the cation, then the anion; a metal with more than one charge takes the charge "
        "the anions balance, in Roman numerals",
    ),
    (
        "coordination_complex",
        "inorganic",
        "Additive coordination name",
        "oxidation state = complex charge − ligand charges",
    ),
    ("boiling_elevation", "solutions", "Boiling-point elevation", "ΔTb = i Kb m"),
    ("freezing_depression", "solutions", "Freezing-point depression", "ΔTf = i Kf m"),
    (
        "solution_boiling_point",
        "solutions",
        "Boiling point of a solution",
        "Tb = Tb° + ΔTb, where ΔTb = i Kb m",
    ),
    (
        "solution_freezing_point",
        "solutions",
        "Freezing point of a solution",
        "Tf = Tf° − ΔTf, where ΔTf = i Kf m",
    ),
    ("osmotic_pressure", "solutions", "van 't Hoff equation", "Π = iMRT"),
    ("raoult", "solutions", "Raoult's law", "P = X P°"),
    ("henry", "solutions", "Henry's law", "C = kH × P"),
    ("calibration", "analytical", "Linear calibration", "c = (signal − intercept) / slope"),
    ("gravimetric", "analytical", "Gravimetric factor", "mass = precipitate × factor"),
    (
        "standard_addition",
        "analytical",
        "One-point standard addition",
        "C = (Ix / (Ispike − Ix)) × Cstd × Vstd / Vsample",
    ),
    ("mass_defect", "nuclear", "Nuclear mass defect", "Δm = Z m_p + (A − Z) m_n − m"),
    ("crystal_field", "inorganic", "Crystal-field spin state", "μ = √(n(n + 2))"),
    (
        "standard_deviation",
        "analytical",
        "Sample standard deviation",
        "s = √(Σ(x − x̄)^2 / (n − 1))",
    ),
    ("standard_error", "analytical", "Standard error", "SE = s / √n"),
    (
        "percent_error",
        "analytical",
        "Percent error",
        "% error = |experimental − accepted| / |accepted| × 100",
    ),
    (
        "relative_uncertainty",
        "analytical",
        "Uncertainty propagation",
        "Δz/z = √((Δa/a)^2 + (Δb/b)^2)",
    ),
    ("chromatography_rf", "analytical", "Chromatography Rf", "Rf = spot distance / solvent front"),
    ("lod", "analytical", "Limit of detection", "LOD = 3s/m"),
    ("loq", "analytical", "Limit of quantitation", "LOQ = 10s/m"),
    ("capacity_factor", "analytical", "Capacity factor", "k' = (tR − tM) / tM"),
    ("selectivity", "analytical", "Selectivity", "α = k2 / k1"),
    ("resolution", "analytical", "Chromatographic resolution", "Rs = 2 (tR2 − tR1) / (w1 + w2)"),
    ("plate_number", "analytical", "Theoretical plates", "N = 16 (tR / w)^2"),
    ("plate_height", "analytical", "Plate height", "H = L / N"),
    ("iupac_name", "organic", "IUPAC name", "PubChem's IUPACName for the structure's SMILES"),
    ("structure", "organic", "Structure", "PubChem's canonical SMILES for the named compound"),
    (
        "named_reaction",
        "organic",
        "Reaction rule",
        "apply the one reaction rule that gives a single product; two possible products decline",
    ),
    (
        "ir_ranges",
        "spectroscopy",
        "IR correlation table",
        "look up each recognized group's textbook absorption range",
    ),
    (
        "ir_peak",
        "spectroscopy",
        "IR correlation table",
        "list every group whose range contains the peak; one peak does not choose a structure",
    ),
    (
        "nmr_ranges",
        "spectroscopy",
        "¹H NMR correlation table",
        "look up each recognized group's textbook chemical-shift range",
    ),
    (
        "nmr_peak",
        "spectroscopy",
        "¹H NMR correlation table",
        "list every group whose range contains the shift; one peak does not choose a structure",
    ),
    ("nmr_splitting", "spectroscopy", "n+1 rule", "lines = neighbors + 1"),
    (
        "molecular_ion",
        "spectroscopy",
        "Molecular ion",
        "add the masses of each element's most abundant isotope, not the average atomic masses",
    ),
    ("michaelis_menten", "biochemistry", "Michaelis–Menten equation", "v = Vmax[S] / (Km + [S])"),
    (
        "average_atomic_mass",
        "amounts",
        "Average atomic mass",
        "A = Σ mᵢ × (abundanceᵢ / 100)",
    ),
    (
        "electron_configuration",
        "structure",
        "Aufbau principle",
        "fill the subshells in the order 1s 2s 2p 3s 3p 4s 3d 4p 5s 4d 5p 6s 4f 5d 6p; "
        "the element table keeps the exceptions (Cr, Cu)",
    ),
)

# A one-line law declares its identity with its arithmetic (formula_laws), once.
_FORMULA_ROWS = tuple(
    (law.op, law.kind, law.law_name, law.formula) for law in FORMULA_LAWS.values()
)

CATALOG: dict[str, FormulaSpec] = {}
for _operation, _kind, _law, _formula in (*_ROWS, *_FORMULA_ROWS):
    if _operation in CATALOG:
        raise RuntimeError(f"duplicate chemistry formula {_operation}")
    CATALOG[_operation] = _spec(_operation, _kind, _law, _formula)


def check_operation(kind: str, operation: str) -> None:
    """Refuse an operation the catalog does not declare, or one it files under another kind."""
    spec = CATALOG.get(operation)
    if spec is None:
        raise ValueError(f"{operation!r} is not a chemistry operation")
    if spec.kind != kind:
        raise ValueError(f"{operation!r} is not a {kind!r} chemistry operation")


def formula_spec(operation: str) -> FormulaSpec | None:
    return CATALOG.get(operation)


def law_name(operation: str) -> str:
    """The law an operation's answer names, e.g. ``Dilution equation`` for ``dilution``."""
    return stated(operation)[0]


def stated(operation: str) -> tuple[str, str]:
    """Law name and base formula printed for an operation whose formula does not change."""
    spec = formula_spec(operation)
    if spec is None:
        raise KeyError(operation)
    return spec.law_name, spec.base_formula
