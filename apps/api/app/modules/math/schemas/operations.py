"""The operation names each maths kind accepts, written once.

``MathIntent``, the solver inputs and results, and the matchers all read these, so a new
statistic, matrix operation, solid or fraction procedure is one edit here plus its solver.
A ``Literal`` nested in another is flattened in order, so the composed ones below are the
same types as their values written out.
"""

from __future__ import annotations

from typing import Literal, get_args

# The statistics one list can ask for together ("mean and standard deviation of …").
SummaryStatsOp = Literal[
    "mean", "median", "mode", "variance", "stdev", "sample_stdev", "sample_variance", "range"
]
SUMMARY_STATS: frozenset[str] = frozenset(get_args(SummaryStatsOp))
# Every statistic of one list.
StatsOp = Literal[SummaryStatsOp, "iqr", "quartiles", "percentile"]
# Two explicit lists of equal length.
BivariateStatsOp = Literal["correlation", "covariance", "sample_covariance", "linear_regression"]
StatisticsOp = Literal[StatsOp, BivariateStatsOp]

CombinatoricsOp = Literal["factorial", "combinations", "permutations"]

# What the number-theory solver computes; a two-congruence CRT is read and answered apart.
NumberTheorySolveOp = Literal[
    "gcd", "lcm", "factorize", "is_prime", "mod", "mod_inverse", "totient"
]
NumberTheoryOp = Literal[NumberTheorySolveOp, "crt"]

MatrixOp = Literal[
    "determinant",
    "inverse",
    "multiply",
    "rref",
    "eigenvalues",
    "eigenvectors",
    "rank",
    "nullspace",
    "columnspace",
    "rowspace",
    "diagonalize",
    "add",
    "transpose",
]

SolidShape = Literal["cube", "rectangular_prism", "cylinder", "cone", "sphere", "pyramid"]

FractionOp = Literal[
    "simplify",
    "equivalent",
    "add",
    "subtract",
    "multiply",
    "divide",
    "mixed_to_improper",
    "improper_to_mixed",
    "of_quantity",
    "compare",
]
