"""Verified torque operations."""

from __future__ import annotations

from app.services.law_binding.spec import FormulaSpec, FormulaVariant, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "torque",
        "torque",
        "Torque formula",
        "\\tau",
        base_latex="\\tau = Fd\\sin(\\theta)",
        variables=(
            var("F", "F", "newton"),
            var("angle", r"\theta", dimensionless=True),
            var("d", "d", "meter"),
        ),
    ),
    formula(
        "moment_balance",
        "torque",
        "Principle of moments",
        "d_2",
        base_latex="F_1d_1 = F_2d_2",
        variants=(FormulaVariant(present=frozenset({"d2"}), result_symbol="F_2"),),
        variables=(
            var("F1", "F_1", "newton"),
            var("F2", "F_2", "newton"),
            var("d1", "d_1", "meter"),
            var("d2", "d_2", "meter"),
            var("m1", "m_1", "kilogram"),
            var("m2", "m_2", "kilogram"),
        ),
    ),
    formula(
        "lever_arm",
        "torque",
        "Torque formula",
        "d",
        base_latex="\\tau = Fd\\sin(\\theta)",
        variables=(
            var("F", "F", "newton"),
            var("tau", r"\tau", "newton * meter"),
        ),
    ),
    formula(
        "net_torque",
        "torque",
        "Net-torque equation",
        "\\tau_{net}",
        variables=(
            var("tau1", r"\tau_1", "newton * meter"),
            var("tau2", r"\tau_2", "newton * meter"),
            var("tau3", r"\tau_3", "newton * meter"),
        ),
    ),
)
