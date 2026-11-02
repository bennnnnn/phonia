"""Corpus rows for gases, heat, kinetics, nuclear, electrochemistry, equilibrium and structure.

Worked the same way as ``corpus.py``: each value is the textbook formula, not a read-back.
"""

from __future__ import annotations

import math

from app.tests.modules.chemistry.corpus_case import (
    CO2,
    CU,
    FARADAY,
    O2,
    R_ATM,
    R_GAS,
    Case,
    H,
    q,
    says,
)

GASES: tuple[Case, ...] = (
    q("What volume does 2 mol of gas occupy at 300 K and 1 atm?", 2 * R_ATM * 300, "L"),
    q(
        "A gas at 2 atm occupies 4 L. What is its volume at 1 atm at constant temperature?",
        2 * 4 / 1,
        "L",
    ),
    q(
        "A gas occupies 2 L at 300 K. Find its volume at 600 K at constant pressure.",
        2 * 600 / 300,
        "L",
    ),
    q("Find the pressure of 1 mol of gas in 10 L at 273 K.", R_ATM * 273 / 10, "atm"),
    q(
        "The partial pressures are 0.3 atm, 0.5 atm and 0.2 atm. Find the total pressure.",
        0.3 + 0.5 + 0.2,
        "atm",
    ),
    q(
        "A gas occupies 1 L at 1 atm and 273 K. Find its volume at 2 atm and 546 K.",
        1 * 1 * 546 / (273 * 2),
        "L",
    ),
    q("How many moles of gas are in 5 L at 2 atm and 300 K?", 2 * 5 / (R_ATM * 300), "mol"),
    q("Find the density of CO2 gas at 1 atm and 273 K.", CO2 / (R_ATM * 273), "g/L"),
    q("Compare the rates of effusion of H2 and O2 using Graham's law.", math.sqrt(O2 / (2 * H))),
)

THERMOCHEMISTRY: tuple[Case, ...] = (
    q(
        "How much heat is needed to raise the temperature of 100 g of water by 10 °C? "
        "c = 4.18 J/g°C",
        100 * 4.18 * 10,
        "J",
    ),
    q(
        "Calculate ΔG at 298 K if ΔH = -100 kJ/mol and ΔS = -200 J/mol·K.",
        -100 - 298 * -0.200,
        "kJ/mol",
    ),
    q("How much heat is needed to melt 50 g of ice? ΔHfus = 334 J/g", 50 * 334, "J"),
    q(
        "A 50 g piece of metal at 100 °C is dropped into 100 g of water at 20 °C. "
        "The final temperature is 25 °C. Find the specific heat of the metal.",
        # All the heat the water gained (100 g, 4.184 J/(g·°C), 5 °C) left the metal.
        100 * 4.184 * 5 / (50 * 75),
        "J/(g·°C)",
    ),
)

KINETICS_AND_NUCLEAR: tuple[Case, ...] = (
    q("A first-order reaction has k = 0.0693 s^-1. Find its half-life.", math.log(2) / 0.0693, "s"),
    q(
        "A first-order reaction has k = 0.1 s^-1 and [A]0 = 1 M. Find [A] after 10 s.",
        math.exp(-1),
        "mol/L",
    ),
    q("The half-life of a first-order reaction is 20 min. Find k.", math.log(2) / 20, "min⁻¹"),
    q(
        "A rate constant is 0.01 s^-1 at 300 K and 0.04 s^-1 at 320 K. Find the activation energy.",
        R_GAS * math.log(4) / (1 / 300 - 1 / 320) / 1000,
        "kJ/mol",
    ),
    q(
        "A zero-order reaction has k = 0.01 M/s and [A]0 = 1 M. Find [A] after 50 s.",
        1 - 0.01 * 50,
        "mol/L",
    ),
    q(
        "A second-order reaction has k = 0.5 M^-1 s^-1 and [A]0 = 1 M. Find [A] after 2 s.",
        1 / (1 + 0.5 * 2),
        "mol/L",
    ),
    q(
        "A 100 g sample has a half-life of 5 years. How much remains after 15 years?",
        100 * 0.5 ** (15 / 5),
        "g",
    ),
    says("Complete the nuclear equation: 238U -> 234Th + ?", "4He"),
    q(
        "Find the decay constant of carbon-14 if its half-life is 5730 years.",
        math.log(2) / 5730,
        "1/yr",
    ),
    q(
        "Vmax = 10 μmol/min, Km = 2 mM and [S] = 2 mM. Find the reaction rate.",
        10 * 2 / (2 + 2),
        label="v",
    ),
)

ELECTROCHEMISTRY: tuple[Case, ...] = (
    q("Find the standard cell potential of a zinc-copper galvanic cell.", 0.34 + 0.76, "V"),
    q("Find ΔG° for a cell with n = 2 and E° = 1.10 V.", -2 * FARADAY * 1.10 / 1000, "kJ/mol"),
    q(
        "How many grams of Cu are deposited by a current of 2 A for 1 hour from Cu2+?",
        2 * 3600 / (2 * FARADAY) * CU,
        "g",
    ),
    q(
        "A cell has E° = 1.10 V, n = 2 and Q = 0.01 at 298 K. Find E.",
        1.10 - R_GAS * 298 / (2 * FARADAY) * math.log(0.01),
        "V",
    ),
    q(
        "How long must a current of 5 A flow to deposit 10 g of Cu?",
        10 / CU * 2 * FARADAY / 5,
        "s",
    ),
)

EQUILIBRIUM: tuple[Case, ...] = (
    q(
        "For N2 + 3H2 ⇌ 2NH3, [N2] = 0.5 M, [H2] = 1.5 M and [NH3] = 0.2 M. Find Kc.",
        0.2**2 / (0.5 * 1.5**3),
        label="Kc",
    ),
    q(
        "For N2 + 3H2 ⇌ 2NH3, Kc = 0.5 at 500 K. Find Kp.",
        0.5 * (R_ATM * 500) ** -2,
        label="Kp",
    ),
    q(
        "For H2 + I2 ⇌ 2HI, Kc = 50 and the initial [H2] = [I2] = 1.0 M. "
        "Find the equilibrium concentrations.",
        2 * math.sqrt(50) / (2 + math.sqrt(50)),
        "mol/L",
        label="[HI]",
    ),
)

STRUCTURE_AND_ANALYSIS: tuple[Case, ...] = (
    says("What is the shape of NH3?", "trigonal pyramidal"),
    says("What is the oxidation state of S in H2SO4?", "S = +6"),
    says("What is the molecular geometry of CO2?", "linear"),
    says("What is the electron configuration of Fe?", "3d^6"),
    q(
        "The measured value is 9.8 and the accepted value is 10.0. Find the percent error.",
        abs(9.8 - 10.0) / 10.0 * 100,
        "%",
    ),
    q(
        "A spot travels 3 cm and the solvent front travels 6 cm. Find the Rf value.",
        3 / 6,
        label="Rf",
    ),
)

CASES: tuple[Case, ...] = (
    *GASES,
    *THERMOCHEMISTRY,
    *KINETICS_AND_NUCLEAR,
    *ELECTROCHEMISTRY,
    *EQUILIBRIUM,
    *STRUCTURE_AND_ANALYSIS,
)
