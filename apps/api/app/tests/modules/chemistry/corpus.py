"""Chemistry QA corpus: school questions with independently worked answers.

Each expected value is the textbook formula evaluated in ``corpus_case`` units, not a
solver read-back. The test in ``test_chemistry_corpus.py`` holds two lines:

* a verified answer is never wrong: it matches the worked value to the figures it shows, or
  the question declines;
* coverage only goes up: ``COVERAGE_FLOOR`` counts the cases answered today.

Add a row whenever a phrasing is fixed or found wrong. ``MUST_DECLINE`` lists questions any
single answer to would mislead.
"""

from __future__ import annotations

import math

from app.tests.modules.chemistry import corpus_physical
from app.tests.modules.chemistry.corpus_case import (
    AVOGADRO,
    CO2,
    H2O,
    NACL,
    O2,
    R_ATM,
    R_GAS,
    C,
    Case,
    H,
    O,
    S,
    q,
    says,
)

__all__ = ["ANSWERABLE", "COVERAGE_FLOOR", "MUST_DECLINE", "NOT_CHEMISTRY", "Case"]


def _weak(constant: float, concentration: float) -> float:
    """x of a weak acid or base from the exact quadratic x^2 + Kx - KC = 0."""
    return (-constant + math.sqrt(constant**2 + 4 * constant * concentration)) / 2


AMOUNTS: tuple[Case, ...] = (
    q("What is the molar mass of H2SO4?", 2 * H + S + 4 * O, "g/mol"),
    q("How many moles are in 36 g of water?", 36 / H2O, "mol"),
    q("How many moles are in 36 g of H2O?", 36 / H2O, "mol"),
    q("Convert 2.5 mol of CO2 to grams.", 2.5 * CO2, "g"),
    q("How many molecules are in 0.5 mol of H2O?", 0.5 * AVOGADRO, "particles"),
    q("Calculate the percent composition of carbon in CO2.", C / CO2 * 100, "%"),
    says("A compound is 40.0% C, 6.7% H and 53.3% O. Find its empirical formula.", "CH2O"),
    says(
        "The empirical formula is CH2O and the molar mass is 180 g/mol. "
        "Find the molecular formula.",
        "C6H12O6",
    ),
    q(
        "The theoretical yield is 50 g and the actual yield is 45 g. Find the percent yield.",
        45 / 50 * 100,
        "%",
    ),
    q(
        "What is the atom economy of CH3COOCH3 in CH3COOH + CH3OH -> CH3COOCH3 + H2O?",
        # 74.079 / (60.052 + 32.042) from the element table, not a solver read-back.
        (3 * C + 6 * H + 2 * O) / ((2 * C + 4 * H + 2 * O) + (C + 4 * H + O)) * 100,
        "%",
    ),
    q(
        "What is the total vapor pressure if the mole fraction of A is 0.400, "
        "the vapor pressure of A is 0.800 atm, the mole fraction of B is 0.600, "
        "and the vapor pressure of B is 0.400 atm?",
        0.400 * 0.800 + 0.600 * 0.400,
        "atm",
    ),
    q("How many atoms are in 2 mol of He?", 2 * AVOGADRO, "atoms"),
    q("How many grams are in 3.01 × 10^23 molecules of O2?", 3.01e23 / AVOGADRO * O2, "g"),
    q("How many grams of oxygen are in 10 g of H2O?", 10 * O / H2O, "g"),
    says(
        "Combustion of a 0.60052 g sample of a compound containing only C, H, and O "
        "produced 0.88018 g of CO2 and 0.36030 g of H2O. What is the empirical formula?",
        "CH2O",
    ),
    says(
        "A 2.49677 g sample of a hydrate of CuSO4 leaves 1.59602 g of anhydrous CuSO4. "
        "How many waters of hydration?",
        "CuSO4\u00b75H2O",
    ),
    q(
        "Chlorine has isotopes 35Cl (75.77%) and 37Cl (24.23%). Find its average atomic mass.",
        # The isotopes' masses, 34.969 and 36.966 u, not their mass numbers.
        34.969 * 0.7577 + 36.966 * 0.2423,
    ),
)

STOICHIOMETRY: tuple[Case, ...] = (
    q(
        "How many grams of water are produced from 4 g of H2 in 2H2 + O2 -> 2H2O?",
        4 / (2 * H) * H2O,
        "g",
    ),
    q("N2 + 3H2 -> 2NH3. How many moles of NH3 form from 3 mol of H2?", 3 * 2 / 3, "mol"),
    says("Balance: Fe + O2 -> Fe2O3", "4 Fe + 3 O2 -> 2 Fe2O3"),
    says("Balance C3H8 + O2 -> CO2 + H2O", "C3H8 + 5 O2 -> 3 CO2 + 4 H2O"),
    says(
        "Balance KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2",
        "2 KMnO4 + 16 HCl -> 2 KCl + 2 MnCl2 + 8 H2O + 5 Cl2",
    ),
    q(
        "In 2H2 + O2 -> 2H2O, 10 g of H2 reacts with 64 g of O2. Find the limiting reagent.",
        2 * (64 / O2) * H2O,
        "g",
        text="Limiting reagent = O2",
    ),
    q(
        "How many liters of CO2 at STP are produced by burning 1 mol of CH4?",
        R_ATM * 273.15,
        "L",
    ),
    q(
        "How much heat is released when 2 mol of CH4 burns? ΔH = -890 kJ/mol",
        2 * -890,
        "kJ",
    ),
)

SOLUTIONS: tuple[Case, ...] = (
    q("What is the molarity of a solution with 0.5 mol NaCl in 2 L of solution?", 0.5 / 2, "mol/L"),
    q("How many grams of NaCl are needed to make 500 mL of 0.2 M solution?", 0.1 * NACL, "g"),
    q(
        "50 mL of 2 M HCl is diluted to 200 mL. What is the new concentration?",
        2 * 50 / 200,
        "mol/L",
    ),
    q("What volume of 6 M HCl is needed to make 500 mL of 1.5 M HCl?", 1.5 * 500 / 6, "mL"),
    q("Find the molality of 10 g of NaCl dissolved in 500 g of water.", 10 / NACL / 0.5, "mol/kg"),
    q(
        "Find the freezing point depression of 0.5 m glucose in water. Kf = 1.86 °C/m.",
        1.86 * 0.5,
        "°C",
    ),
    q(
        "Find the boiling point elevation of a 1 m NaCl solution. Kb = 0.512 °C/m, i = 2.",
        2 * 0.512,
        "°C",
    ),
    q("Find the osmotic pressure of 0.1 M glucose at 25 °C.", 0.1 * R_ATM * 298.15, "atm"),
    q("Find the mass percent of 5 g of sugar dissolved in 95 g of water.", 5 / (5 + 95) * 100, "%"),
    q(
        "What is the ppm of 2.50 mg of solute in 1.00 kg of solution?",
        2.50e-3 / 1000 * 1e6,
        "ppm",
    ),
    q(
        "What is the ppb of 2.50 mg of solute in 1.00 kg of solution?",
        2.50e-3 / 1000 * 1e9,
        "ppb",
    ),
    q(
        "What is the volume percent of 25.0 mL of solute in 500.0 mL of solution?",
        25.0 / 500.0 * 100,
        "%",
    ),
    q(
        "What is the mass/volume percent of 5.00 g of solute in 250 mL of solution?",
        5.00 / 250 * 100,
        "%",
    ),
    q(
        "Find the mole fraction of ethanol in a solution of 2 mol ethanol and 8 mol water.",
        2 / (2 + 8),
    ),
    q(
        "25.0 mL of NaOH is neutralized by 20.0 mL of 0.100 M HCl. "
        "Find the concentration of the NaOH.",
        20.0 * 0.100 / 25.0,
        "mol/L",
    ),
    q(
        "A solution has absorbance 0.5, molar absorptivity 100 L/(mol·cm) and path length "
        "1 cm. Find the concentration.",
        0.5 / (100 * 1),
        "mol/L",
    ),
)

ACIDS_AND_BASES: tuple[Case, ...] = (
    q("What is the pH of 0.01 M HCl?", -math.log10(0.01), label="pH"),
    q("What is the pH of 0.001 M NaOH?", 14 + math.log10(0.001), label="pH"),
    q("Find the pH of a solution with [H+] = 3.2 × 10^-4 M.", -math.log10(3.2e-4), label="pH"),
    q(
        "What is the pH of 0.1 M acetic acid? Ka = 1.8 × 10^-5",
        -math.log10(_weak(1.8e-5, 0.1)),
        label="pH",
    ),
    q(
        "What is the pH of 0.1 M NH3? Kb = 1.8 × 10^-5",
        14 + math.log10(_weak(1.8e-5, 0.1)),
        label="pH",
    ),
    q(
        "Find the pH of a buffer of 0.1 M acetic acid and 0.1 M sodium acetate. pKa = 4.74",
        4.74,
        label="pH",
    ),
    q("The pOH of a solution is 4.5. Find the pH.", 14 - 4.5, label="pH"),
    q("Find the pKa if Ka = 1.8 × 10^-5", -math.log10(1.8e-5), label="pKa"),
    q("What is the pH of 0.01 M Ca(OH)2?", 14 + math.log10(0.02), label="pH"),
    q(
        "25 mL of 0.1 M HCl is titrated with 0.1 M NaOH. Find the pH after adding 10 mL of NaOH.",
        -math.log10((2.5 - 1.0) / 35),
        label="pH",
    ),
    q(
        "What is the percent ionization of 0.1 M acetic acid? Ka = 1.8 × 10^-5",
        _weak(1.8e-5, 0.1) / 0.1 * 100,
        "%",
    ),
    q(
        "The Ksp of AgCl is 1.8 × 10^-10. Find its molar solubility.",
        math.sqrt(1.8e-10),
        "mol/L",
    ),
    says(
        "What is the pH of an amphiprotic solution with pKa1 = 4.00 and pKa2 = 9.00?",
        "pH = 6.50",
    ),
    says(
        "What is [A2-] for a diprotic acid with Ka2 = 1.0e-8?",
        "[A2-] = 1.0 × 10^-8 mol/L",
    ),
)

EQUILIBRIUM: tuple[Case, ...] = (
    q(
        "Use the van 't Hoff equation. K1 = 1.00, T1 = 300 K, T2 = 350 K, "
        "and ΔH = 50.0 kJ/mol. What is K2?",
        1.00 * math.exp(-50.0e3 / R_GAS * (1 / 350 - 1 / 300)),
    ),
    q(
        "Use the van 't Hoff equation. K1 = 0.10, T1 = 300 K, K2 = 0.50, "
        "and T2 = 350 K. What is ΔH?",
        -(R_GAS * math.log(0.50 / 0.10) / (1 / 350 - 1 / 300)) / 1000,
        "kJ/mol",
    ),
    q(
        "K = 10 at 298.15 K. What is ΔG°?",
        -(R_GAS * 298.15 * math.log(10)) / 1000,
        "kJ/mol",
    ),
    q(
        "ΔG° = -5.708 kJ/mol at 298.15 K. What is the equilibrium constant?",
        math.exp(5.708e3 / (R_GAS * 298.15)),
    ),
)


EQUATIONS: tuple[Case, ...] = (
    says(
        "Balance the half-reaction MnO4- -> Mn2+ in acidic solution.",
        "MnO4- + 8 H+ + 5 e- -> Mn2+ + 4 H2O",
    ),
)


ANALYTICAL: tuple[Case, ...] = (
    says("What is the LOD when m = 2.00 and s = 0.060?", "LOD = 0.090"),
    says("What is the LOQ when m = 2.00 and s = 0.060?", "LOQ = 0.30"),
    says("What is the capacity factor when tR = 5.00 and tM = 1.00?", "k' = 4.00"),
    says("What is the selectivity when k1 = 2.00 and k2 = 4.00?", "α = 2.00"),
    says("What is Rs when tR1 = 4.00, tR2 = 5.20, w1 = 0.40, and w2 = 0.40?", "Rs = 3.0"),
    says("What is the plate number when tR = 10.0 and w = 1.00?", "N = 1600"),
    says("What is the plate height when L = 16.0 and N = 1600?", "H = 0.0100"),
)


ANSWERABLE: tuple[Case, ...] = (
    *AMOUNTS,
    *STOICHIOMETRY,
    *SOLUTIONS,
    *ACIDS_AND_BASES,
    *EQUILIBRIUM,
    *EQUATIONS,
    *ANALYTICAL,
    *corpus_physical.CASES,
)

MUST_DECLINE: tuple[str, ...] = (
    # Fe and S can share the oxidation numbers more than one way.
    "Balance FeS -> Fe2+ in acidic solution.",
    # Two redox pairs are a full equation, not one half-reaction to complete.
    "Balance MnO4- + Fe2+ -> Mn2+ + Fe3+ in acidic solution.",
    # The second proton of H2SO4 is only partly lost (Ka2 ≈ 0.012): pH 1.0 would be wrong.
    "What is the pH of a 0.05 M H2SO4 solution?",
    # One constant is not an amphiprotic average, and Ka2 = 0.012 is not [A2-] = Ka2.
    "What is the pH of an amphiprotic solution with pKa1 = 4.00?",
    "What is [A2-] when Ka2 = 0.012?",
    # [A2-] = Ka2 cannot exceed the acid, and a trace amphiprotic salt is not the pKa average.
    "What is [A2-] in 1.0e-10 M diprotic H2A with Ka1 = 1e-4 and Ka2 = 1e-8?",
    "What is the pH of a 1e-10 M amphiprotic salt with pKa1 = 4.00 and pKa2 = 9.00?",
    "What is the concentration of H+ in a diprotic acid that also forms A2-? Ka2 = 1e-8",
    # Nitrogen is not a C/H/O combustion, and these product masses outweigh the sample.
    "Combustion of a 0.60052 g sample of a compound containing nitrogen produced "
    "0.88018 g of CO2 and 0.36030 g of H2O. What is the empirical formula?",
    "Combustion of a 0.20000 g sample of a compound containing only C, H, and O produced "
    "0.88018 g of CO2 and 0.36030 g of H2O. What is the empirical formula?",
    # The anhydrous salt is heavier than the sample, so it is not that hydrate.
    "A 1.00000 g sample of a hydrate of CuSO4 leaves 1.59602 g of anhydrous CuSO4. "
    "How many waters of hydration?",
    # No slope is stated, and a retention time before the dead time is not k'.
    "What is the LOD?",
    "What is the capacity factor when tR = 1.00 and tM = 5.00?",
    # Charge balance over every species is not these two steps.
    "What are all the species concentrations for 0.10 M H2A with Ka1 = 1e-3 and Ka2 = 1e-8?",
    # No time unit for k.
    "Find first-order half-life when k=0.2",
    # 310 what: kelvin or Celsius?
    "Use Nernst equation with E°=1.1 V, n=2, Q=10, T=310",
    # A pressure with no unit cannot give Kp.
    "Find Kp for CaCO3(s) -> CaO(s) + CO2(g) when P(CO2)=0.2",
    # Which reagent was added decides whether the pH rises or falls.
    "Buffer after adding: pKa=4.76, HA=0.10 mol, A-=0.10 mol, added=0.02 mol",
    # "5 runs" is a count, not five readings.
    "Find the standard deviation of the Cu2+ readings from 5 runs",
)

NOT_CHEMISTRY: tuple[str, ...] = (
    "my team has great chemistry",
    "the chemistry between them",
    "the half-life of my phone battery",
    "What is 2 to the power of 3?",
    "how many KB is this file",
    "acid reflux remedies",
    "buffer overflow in my C code",
    "precipitation tomorrow in Seattle",
    "kinetic energy of a 2 kg ball",
    "what is compound interest",
    # ppm of a price or a stock is not a concentration.
    "the stock rose 3 ppm",
    # A capital M after a number is a molarity only before a real formula.
    "3 M Company stock rose 2% today.",
    "We sold 5 M units in 2024.",
    "neutralize the threat before it spreads",
    "the diffusion of new ideas through a company",
)

# Answered and correct today. Raise it whenever coverage grows; never lower it.
COVERAGE_FLOOR = 103
