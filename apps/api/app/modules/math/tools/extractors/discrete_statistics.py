"""Discrete-math and statistics intent extractors."""

from __future__ import annotations

from typing import cast

from app.modules.math.schemas import MathIntent
from app.modules.math.schemas.operations import SUMMARY_STATS, SummaryStatsOp


def _extract_statistics_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math.match.statistics import bivariate_stats_signal
    from app.services.text_match import word_index

    paired = bivariate_stats_signal(cleaned)
    if paired is not None:
        paired_op, paired_numbers, paired_numbers_b = paired
        return MathIntent(
            kind="statistics",
            stats_op=paired_op,
            stats_numbers=paired_numbers,
            stats_numbers_b=paired_numbers_b,
            operation="solve",
        )

    signal = mtm.stats_signal(cleaned)
    if signal is None:
        return None
    stat_op, numbers = signal
    from app.modules.math.match.discrete import requested_summary_stats

    requested = requested_summary_stats(cleaned)
    if len(requested) >= 2:
        if not all(op in SUMMARY_STATS for op in requested):
            return None
        return MathIntent(
            kind="statistics",
            stats_op=requested[0],
            stats_ops=cast(list[SummaryStatsOp], list(requested)),
            stats_numbers=numbers,
            operation="solve",
        )
    percentile_n = None
    if stat_op == "percentile":
        idx = word_index(cleaned.lower(), "percentile")
        if idx == -1:
            return None
        j = idx
        while j > 0 and cleaned[j - 1].isspace():
            j -= 1
        if j >= 2 and cleaned[j - 2 : j].lower() in {"st", "nd", "rd", "th"}:
            k = j - 2
            while k > 0 and cleaned[k - 1].isdigit():
                k -= 1
            if k < j - 2:
                percentile_n = int(cleaned[k : j - 2])
        if percentile_n is None:
            return None
    return MathIntent(
        kind="statistics",
        stats_op=stat_op,
        stats_numbers=numbers,
        combo_n=percentile_n,
        operation="solve",
    )


def _extract_combinatorics_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    signal = mtm.combinatorics_signal(cleaned)
    if signal is None:
        return None
    op, n, k = signal
    return MathIntent(kind="combinatorics", combo_op=op, combo_n=n, combo_k=k, operation="solve")


def _extract_number_theory_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm
    from app.modules.math.match.discrete import crt_signal

    crt = crt_signal(cleaned)
    if crt is not None:
        rem_a, mod_m, rem_b, mod_n = crt
        return MathIntent(
            kind="number_theory",
            numtheory_op="crt",
            numtheory_a=rem_a,
            numtheory_b=mod_m,
            vec_a=[float(rem_a), float(mod_m), float(rem_b), float(mod_n)],
            operation="solve",
        )
    signal = mtm.number_theory_signal(cleaned)
    if signal is None:
        from app.modules.math.match.discrete import gcd_lcm_list_signal

        listed = gcd_lcm_list_signal(cleaned)
        if listed is None:
            return None
        list_op, values = listed
        return MathIntent(
            kind="number_theory",
            numtheory_op=list_op,
            numtheory_a=values[0],
            numtheory_b=values[1],
            numtheory_values=values,
            operation="solve",
        )
    op, a, b = signal
    return MathIntent(
        kind="number_theory", numtheory_op=op, numtheory_a=a, numtheory_b=b, operation="solve"
    )


DISCRETE_STATISTICS_EXTRACTORS = (
    _extract_statistics_intent,
    _extract_combinatorics_intent,
    _extract_number_theory_intent,
)
