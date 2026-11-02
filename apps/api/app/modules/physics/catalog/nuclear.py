"""Verified radioactive-decay operations beyond the remaining mass."""

from __future__ import annotations

from app.modules.physics.catalog.modern import ELAPSED, HALF_LIFE, HALF_LIFE_CUES
from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

_LAW = "Radioactive-decay law"

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "half_life_fraction",
        "modern",
        _LAW,
        r"\frac{N}{N_0}",
        base_latex=r"\frac{N}{N_0} = \left(\frac{1}{2}\right)^{t/T_{1/2}}",
        expression="(1/2)**(elapsed/half_life)",
        variables=(ELAPSED, HALF_LIFE),
        binding=Binding(
            asks=("fraction", "proportion"),
            result=("dimensionless",),
            inputs=(frozenset({"elapsed", "half_life"}),),
            cues=HALF_LIFE_CUES,
            nonnegative=True,
        ),
    ),
    # How long until a fraction is left: t = T½ log₂(1/fraction). 1/16 is
    # four half-lives: 22,920 years for carbon-14.
    formula(
        "decay_time_from_fraction",
        "modern",
        _LAW,
        "t",
        base_latex=r"\frac{N}{N_0} = \left(\frac{1}{2}\right)^{t/T_{1/2}}",
        expression="half_life*log(1/fraction_left)/log(2)",
        variables=(
            HALF_LIFE,
            var(
                "fraction_left",
                r"\frac{N}{N_0}",
                dimensionless=True,
                words=("only", "until", "remains", "remaining", "left", "of the", "of a"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("how long", "time", "how many years", "how much time"),
            result=("second",),
            inputs=(frozenset({"fraction_left", "half_life"}),),
            cues=HALF_LIFE_CUES,
            nonnegative=True,
            # A fraction left is between nothing and all of it.
            requires=("fraction_left", "1 - fraction_left"),
        ),
    ),
    # What is left after a whole number of half-lives: (1/2)ⁿ. Three is 12.5%.
    formula(
        "percent_after_half_lives",
        "modern",
        _LAW,
        r"\frac{N}{N_0}",
        base_latex=r"\frac{N}{N_0} = \left(\frac{1}{2}\right)^{n}",
        expression="100*(1/2)**n_halves",
        variables=(
            var(
                "n_halves",
                "n",
                dimensionless=True,
                words=("half-lives", "half lives", "half-life", "half life"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("percentage", "percent", "what percent"),
            result=("percent",),
            inputs=(frozenset({"n_halves"}),),
            cues=("half-lives", "half lives"),
            nonnegative=True,
        ),
    ),
    formula(
        "fraction_after_half_lives",
        "modern",
        _LAW,
        r"\frac{N}{N_0}",
        base_latex=r"\frac{N}{N_0} = \left(\frac{1}{2}\right)^{n}",
        expression="(1/2)**n_halves",
        variables=(
            var(
                "n_halves",
                "n",
                dimensionless=True,
                words=("half-lives", "half lives", "half-life", "half life"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("fraction", "proportion"),
            result=("dimensionless",),
            inputs=(frozenset({"n_halves"}),),
            cues=("half-lives", "half lives"),
            nonnegative=True,
        ),
    ),
    # A half-life from two activities a time apart: T½ = t ln2 / ln(A₀/A).
    formula(
        "half_life_from_activities",
        "modern",
        _LAW,
        r"T_{1/2}",
        base_latex=r"A = A_0\left(\frac{1}{2}\right)^{t/T_{1/2}}",
        expression="elapsed*log(2)/log(activity_initial/activity_final)",
        variables=(
            var(
                "activity_initial",
                "A_0",
                "1 / second",
                words=("activity of", "initial", "initially", "starts", "from", "has an activity"),
                needs_words=True,
            ),
            var(
                "activity_final",
                "A",
                "1 / second",
                words=(
                    "it's",
                    "it is",
                    "drops to",
                    "falls to",
                    "decreased to",
                    "to",
                    "now",
                    "only",
                ),
                needs_words=True,
            ),
            var("elapsed", "t", "second", words=("after", "later", "in", "for")),
        ),
        binding=Binding(
            asks=("half-life", "half life"),
            result=("second",),
            inputs=(frozenset({"activity_final", "activity_initial", "elapsed"}),),
            cues=("activity", "bq", "becquerel", "counts"),
            nonnegative=True,
            requires=("activity_initial - activity_final", "activity_final"),
        ),
    ),
    formula(
        "decay_constant",
        "modern",
        _LAW,
        r"\lambda",
        base_latex=r"\lambda = \frac{\ln 2}{T_{1/2}}",
        expression="log(2)/half_life",
        variables=(HALF_LIFE,),
        binding=Binding(
            asks=("decay constant",),
            result=("1 / second",),
            inputs=(frozenset({"half_life"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "activity_from_half_life",
        "modern",
        _LAW,
        "A",
        base_latex=r"A = \lambda N = \frac{\ln 2}{T_{1/2}}N",
        expression="log(2)*n_nuclei/half_life",
        variables=(HALF_LIFE, var("n_nuclei", "N", dimensionless=True)),
        binding=Binding(
            asks=("activity",),
            result=("1 / second",),
            inputs=(frozenset({"half_life", "n_nuclei"}),),
            cues=("nuclei", "atoms"),
            nonnegative=True,
            shown_unit="Bq",
        ),
    ),
    formula(
        "mean_lifetime",
        "modern",
        _LAW,
        r"\tau",
        base_latex=r"\tau = \frac{1}{\lambda} = \frac{T_{1/2}}{\ln 2}",
        expression="half_life/log(2)",
        variables=(HALF_LIFE,),
        binding=Binding(
            asks=("mean life", "mean lifetime", "average lifetime", "average life"),
            result=("second",),
            inputs=(frozenset({"half_life"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "decay_elapsed",
        "modern",
        "Radioactive decay time",
        "t",
        base_latex=r"t = \frac{1}{\lambda}\ln\frac{N_0}{N}",
        expression="log(n_initial/n_final)/decay_const",
        variables=(
            var("n_initial", "N_0", dimensionless=True, words=("from",), needs_words=True),
            var("n_final", "N", dimensionless=True, words=("to",), needs_words=True),
            var(
                "decay_const",
                r"\lambda",
                "1 / second",
                words=("decay constant",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("time", "time elapsed", "age"),
            result=("second",),
            inputs=(frozenset({"decay_const", "n_final", "n_initial"}),),
            cues=("decay",),
            nonnegative=True,
        ),
    ),
    formula(
        "nuclear_radius",
        "modern",
        "Nuclear radius",
        "R",
        base_latex=r"R = R_0 A^{1/3}",
        assumptions=(r"R_0 = 1.2\,\mathrm{fm}",),
        expression="1.2e-15*mass_number**(1/3)",
        variables=(
            var(
                "mass_number",
                "A",
                dimensionless=True,
                words=("mass number", "nucleon"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("nuclear radius", "radius"),
            result=("meter",),
            inputs=(frozenset({"mass_number"}),),
            cues=("nuclear radius",),
            nonnegative=True,
        ),
    ),
)
