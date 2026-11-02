"""What the math keyboard types reaches the solver.

Every problem is built from the keys' own output (``$\\frac{1}{2}$``, ``\\sec()``,
``^{\\prime}``, ``\\%``), slots filled the way a student would, and must come back
verified. Reported from the app: ``\\sec``, ``\\csc``, ``\\cot``, ``\\ln(e)``, the prime
key and the percent key all reached the model unverified, and "Plot" after the
``x^{2}`` key drew a chart that failed to parse.
"""

from __future__ import annotations

import pytest

from app.tests.behavior.cases import Case, Expect
from app.tests.behavior.harness import route_case


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "verified"),
    [
        ("$x^{2}-4=0$", "x = \\pm 2"),  # sq+eq
        ("$\\frac{1}{2}+\\frac{1}{3}$", "\\frac{5}{6}"),  # frac
        ("$\\sqrt{16}$", "4"),  # sqrt
        ("$\\sqrt[3]{27}$", "3"),  # nroot
        ("$2^{10}$", "1024"),  # sup
        ("$|-5|$", "5"),  # abs
        ("$12\\times 3\\div 4$", "12 × 3 ÷ 4 = 9"),  # times/div
        ("$2x+1\\leq 7$", "x \\le 3"),  # leq
        ("$\\sin(\\frac{\\pi}{6})$", "\\frac{1}{2}"),  # sin
        ("$\\arcsin(1)$", "\\frac{\\pi}{2}"),  # arcsin
        ("$\\cot^{-1}(1)$", "\\frac{\\pi}{4}"),  # arccot
        ("$\\sinh(0)$", "0"),  # sinh
        ("$\\sin(30^{\\circ})$", "\\frac{1}{2}"),  # deg
        ("$\\int x^{2}\\,dx$", "\\frac{x^{3}}{3} + C"),  # int
        ("$\\int_{0}^{1}x^{2}\\,dx$", "\\frac{1}{3}"),  # dint
        ("$\\frac{d}{dx}(x^{3})$", "3 x^{2}"),  # der
        ("$\\frac{d^{2}}{dx^{2}}(x^{4})$", "12 x^{2}"),  # der2
        ("$\\frac{\\partial}{\\partial x}(x^{2}y)$", "2 x y"),  # partial
        ("$\\sum_{n=1}^{10}n$", "55"),  # sum
        ("$\\prod_{k=1}^{5}k$", "120"),  # prod
        ("$\\lim_{x\\to 0}\\frac{\\sin(x)}{x}$", "1"),  # lim
        ("$\\binom{5}{2}$", "10"),  # binom
        ("$P(5,2)$", "20"),  # perm
        ("$\\log(100)$", "2"),  # log
        ("$\\ln(e^{2})$", "2"),  # ln
        ("$\\log_{2}(8)$", "3"),  # logn
        ("$\\exp(0)$", "1"),  # exp
        ("$5!$", "5! = 5 × 4 × 3 × 2 × 1 = 120"),  # fact
        ("$(2+\\mathrm{i})(2-\\mathrm{i})$", "5"),  # imag
        ("$17\\bmod 5$", "2"),  # mod
        ("$\\lfloor 3.7 \\rfloor$", "3"),  # floor
        ("$20\\%$ of 50", "10"),  # percent
        ("$\\lim_{x\\to \\infty}\\frac{1}{x}$", "0"),  # to+infty
        ("$f(x)=x^{3}$, find $f^{\\prime}(x)$", "3 x^{2}"),  # prime
        ("$\\frac{d}{dt}(t^{2})$", "2 t"),  # ddt
        ("$\\tan(\\frac{\\pi}{4})$", "1"),  # tan
        ("$\\sec(\\frac{\\pi}{3})$", "2"),  # sec
        ("$\\csc(\\frac{\\pi}{6})$", "2"),  # csc
        ("$\\cot(\\frac{\\pi}{4})$", "1"),  # cot
        ("$\\cosh(0)$", "1"),  # cosh
        ("$\\sech(0)$", "1"),  # sech
        ("$\\sinh^{-1}(0)$", "0"),  # arcsinh
        ("$\\sec^{-1}(2)$", "\\frac{\\pi}{3}"),  # arcsec
        ("$\\csc^{-1}(2)$", "\\frac{\\pi}{6}"),  # arccsc
        ("$\\arctan(1)$", "\\frac{\\pi}{4}"),  # arctan
        ("$|x-3|=5$", "x = -2 \\text{ or } x = 8"),  # abs eq
        ("$\\sqrt[3]{x}=2$", "x = 8"),  # nroot eq
        ("$\\log_{2}(x)=5$", "x = 32"),  # logn eq
        ("$e^{0}$", "1"),  # euler
        ("$10^{3}$", "1000"),  # tenpow
        ("$\\ln(e)$", "1"),  # e-const
        ("simplify $6:8$", "3:4"),  # ratio
        ("$3x-2\\geq 4$", "x \\ge 2"),  # geq
        ("$x^{2}<9$", "-3 < x < 3"),  # lt
        ("$\\cos(\\frac{2\\pi}{3})$", "- \\frac{1}{2}"),  # pi-over
        ("$\\sin(2\\pi )$", "0"),  # two-pi
        ("$x^{2}=9$", "x = \\pm 3"),  # pm solve
    ],
)
async def test_keyboard_problem_is_verified(prompt: str, verified: str) -> None:
    route = await route_case(Case("keyboard", "math", prompt, Expect(), ""))

    assert route.solved
    assert route.verified_answer == verified


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["Plot", "plot it", "graph it"])
async def test_plot_after_the_x_squared_key_graphs_x_squared(prompt: str) -> None:
    history = (
        ("user", "$x^{2}$"),
        ("assistant", "Do you want me to plot it, expand it, or solve $x^2 =$ something?"),
    )
    route = await route_case(Case("keyboard", "math", prompt, Expect(), "", history=history))

    assert route.solved
    assert "Function samples for x^2" in route.verified_text
    # Answered with the graph itself: the model, handed the samples, wrote out its reasoning.
    assert route.instant == "solver"
    assert route.instant_text.startswith("```graph")
