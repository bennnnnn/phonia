"""The asked values worked through the catalog's formulas."""

from __future__ import annotations

import math

import pytest

from app.modules.money.catalog import product
from app.modules.money.read import MoneyRequest
from app.modules.money.solve import work


def _request(key: str, **values: float) -> MoneyRequest:
    return MoneyRequest(product(key), dict(values))


def test_work_fills_the_default_term_and_says_so() -> None:
    worked = work(_request("mortgage", amount=300000, rate=1), None)
    assert worked is not None
    assert worked.values["years"] == 30 and worked.assumed == ("years",)
    assert math.isclose(worked.outputs["payment"] or 0, 964.9185613, rel_tol=1e-9)
    assert math.isclose(worked.outputs["total"] or 0, 347370.6821, rel_tol=1e-9)


def test_work_takes_todays_average_when_no_rate_was_given() -> None:
    worked = work(_request("mortgage", amount=300000), 6.274)
    assert worked is not None
    assert worked.values["rate"] == 6.27 and "rate" in worked.assumed


def test_work_needs_a_rate_from_somewhere() -> None:
    assert work(_request("mortgage", amount=300000), None) is None


def test_work_needs_every_input_without_a_default() -> None:
    assert work(_request("card", balance=5000, apr=22), None) is None


@pytest.mark.parametrize(
    ("values", "months"),
    [({"balance": 5000, "apr": 22.8, "payment": 200}, 34.2346950), ({"balance": 1200, "apr": 0, "payment": 100}, 12.0)],
)  # fmt: skip
def test_work_counts_the_months_to_clear_a_card(values: dict[str, float], months: float) -> None:
    worked = work(_request("card", **values), None)
    assert worked is not None and math.isclose(worked.outputs["months"] or 0, months, rel_tol=1e-7)


def test_work_says_a_payment_below_the_interest_never_clears_the_card() -> None:
    worked = work(_request("card", balance=5000, apr=24, payment=100), None)
    assert worked is not None
    assert worked.outputs["months"] is None and worked.outputs["interest"] is None


def test_work_grows_savings_with_monthly_deposits() -> None:
    worked = work(_request("savings", start=1000, deposit=200, rate=4.5, years=10), None)
    assert worked is not None
    assert math.isclose(worked.outputs["balance"] or 0, 31806.6075113, rel_tol=1e-9)
    assert worked.outputs["deposited"] == 25000


# 2026-10-31, an Ethiopian grade 11 book: "6% per year, compounded quarterly" was worked
# monthly. 3000 at 6% for 7 years quarterly is 3000·1.015^28.
@pytest.mark.parametrize(
    ("per_year", "balance"),
    [
        (4, 3000 * 1.015**28),
        (2, 3000 * 1.03**14),
        (1, 3000 * 1.06**7),
        (365, 3000 * (1 + 0.06 / 365) ** (365 * 7)),
        (12, 3000 * 1.005**84),
    ],
)
def test_savings_compound_as_often_as_the_request_says(per_year: int, balance: float) -> None:
    request = MoneyRequest(
        product("savings"), {"start": 3000, "rate": 6, "years": 7}, settings={"per_year": per_year}
    )
    worked = work(request, None)
    assert worked is not None
    assert math.isclose(worked.outputs["balance"] or 0, balance, rel_tol=1e-9)
    assert math.isclose(worked.outputs["interest"] or 0, balance - 3000, rel_tol=1e-9)


def test_a_monthly_deposit_grows_by_the_months_share_of_the_compounding() -> None:
    """Quarterly at 6%, a deposit made each month grows 1.015^(1/3) a month."""
    request = MoneyRequest(
        product("savings"),
        {"start": 0, "deposit": 100, "rate": 6, "years": 1},
        settings={"per_year": 4},
    )
    worked = work(request, None)
    step = 1.015 ** (1 / 3)
    assert worked is not None
    assert math.isclose(worked.outputs["balance"] or 0, 100 * (step**12 - 1) / (step - 1))
