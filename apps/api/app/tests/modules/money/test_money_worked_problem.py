"""A lesson's money problem is laid out for the student only when every number in it is
the question's own; anyone's own money, advice and choices keep the short reply
(2026-10-31: two Grade 11-12 questions got two lines over a calculator card)."""

from __future__ import annotations

import pytest

from app.modules.money.block import MONEY_REPLY_RULES, MONEY_WORKED_RULES, money_block
from app.modules.money.read import read_money_request
from app.modules.money.solve import work
from app.modules.money.worked_problem import is_worked_problem, lays_out_working


@pytest.mark.parametrize(
    "text",
    [
        "Ato Alula deposited Birr 3,000 in a saving account that pays 6% interest rate per "
        "year. What is the amount at the end of 7 years?",
        "Sara invests $2,000 at 5% compounded annually. How much will she have after 6 years?",
        "A man borrows $12,000 at 9% for 4 years. Find his monthly payment.",
        "A loan of $20,000 at 6% for 5 years. What is the monthly payment?",
        "Tom has a credit card balance of $3,000 at 18% APR and pays $100 a month. How long "
        "until it is paid off?",
        # A textbook's "you" is the reader's exercise, not the asker's own money.
        "Suppose you borrow $10,000 at 5% for 3 years. What is your monthly payment?",
        "If you deposit $1,000 at 6% compounded monthly for 5 years, how much will you have?",
        # Who is in it never decides: a brand states its numbers like a book.
        "Chase offers a car loan at 7% for $30,000 over 5 years. What's the payment?",
        # "which" opening a clause is no choice.
        "Moges wants to buy a house. He has saved Birr 50,000 which he will use as a deposit. "
        "What will his monthly payment be?",
    ],
)
def test_a_number_to_work_out_is_a_worked_problem(text: str) -> None:
    assert is_worked_problem(text)


@pytest.mark.parametrize(
    "text",
    [
        "My sister wants to buy a house for $400,000 at 6.5% for 30 years. What would her "
        "payment be?",
        "Abebe from work asked me what a $20,000 car loan at 7% for 5 years costs",
        "I have $5,000 on my credit card at 22% APR and pay $200 a month. How long?",
        "Our company took a loan of $500,000 at 8% over 10 years. What is the payment?",
        "A customer at my shop wants a $5,000 loan at 10% for 2 years. Payment?",
        "Find the best savings rate for $10,000",
        "The business has a $500,000 loan at 8% over 10 years. Should the owner refinance?",
        "John wants to refinance his $250k mortgage at 7% to 6%, what's his new payment?",
        "Compare a 15 year and 30 year mortgage on $300k at 6%",
        "Which is better, a 15-year at 5.5% or a 30-year at 6.25% on $400,000?",
        "Netflix wants $15/month; savings at 5%",
    ],
)
def test_own_money_advice_or_no_ask_is_not(text: str) -> None:
    assert not is_worked_problem(text)


@pytest.mark.parametrize(
    ("text", "laid_out"),
    [
        # Every value read from the question.
        ("Car loan $25,000 at 7% for 5 years, find monthly payment", True),
        # Compounding the app assumed (monthly: 4,561.11) is not the book's (yearly:
        # 4,510.89), 2026-11-01.
        (
            "Ato Alula deposited Birr 3,000 in a saving account that pays 6% interest rate "
            "per year. What is the amount at the end of 7 years?",
            False,
        ),
        # A term the app assumed would look like the book's own.
        (
            "Ato Alula deposited Birr 3,000 in a saving account at 6% a year. What is the amount?",
            False,
        ),
        # Compounding the question names is read (#2154), and the loan is the price less
        # the money down: every number is the question's.
        (
            "Ato Alula deposited Birr 3,000 in a saving account that pays 6% interest rate "
            "per year, compounded quarterly. What is the amount of interest obtained at the "
            "end of seven years?",
            True,
        ),
        (
            "Moges wants to buy a house that costs Birr 250,000. He has saved Birr 50,000 "
            "which he will use as a deposit, and will finance the rest of the cost by taking "
            "out a loan, amortized over 30 years, at an annual interest rate of 7%. What will "
            "his monthly payment be?",
            True,
        ),
        # A stated sum the numbers never use.
        (
            "Mr. Bekele earns $90,000 a year and takes a $300,000 mortgage at 6.5% for 30 "
            "years. What is the monthly payment?",
            False,
        ),
    ],
)
def test_the_layout_needs_every_number_from_the_question(text: str, laid_out: bool) -> None:
    request = read_money_request(text)
    assert request is not None
    assert lays_out_working(text, request, work(request, None)) is laid_out


# A monthly deposit's timing and a recurring deposit's simple interest are the book's
# convention, never read from the question: no layout (2026-11-01: Rahul's recurring deposit
# laid out as Rs 39,930.10, the ICSE answer Rs 39,885).
@pytest.mark.parametrize(
    "text",
    [
        "Rahul pays Rs 1,000 a month into a recurring deposit at 7% for 3 years. Find the "
        "maturity value.",
        "If you deposit $200 at the end of each month at 6% compounded monthly for 5 years, "
        "how much will you have?",
        "Kebede deposits Birr 500 every month in a savings account at 6% compounded monthly "
        "for 4 years. Find the amount.",
    ],
)
def test_a_monthly_deposit_is_never_laid_out(text: str) -> None:
    request = read_money_request(text)
    assert request is not None and request.values.get("deposit")
    assert not lays_out_working(text, request, work(request, None))


@pytest.mark.parametrize(
    ("text", "worked"),
    [
        # Anyone's quick ask states its values and asks at once: the short reply.
        ("Hey, what would a $15,000 car loan at 9% for 48 months cost per month?", False),
        ("Mortgage $300k at 6.5% 30 years payment?", False),
        ("Hey. What would a $15,000 car loan at 9% for 48 months cost per month?", False),
        ("Quick question: what's the payment on a $300k mortgage at 6.5% for 30 years?", False),
        ("What is the monthly payment on a loan of $20,000 at 6% for 5 years?", False),
        # An exercise sets its values out first, opens on a condition, or orders the work.
        ("A loan of $20,000 at 6% for 5 years. What is the monthly payment?", True),
        ("A loan of $20,000 at 6% for 5 years\nWhat is the monthly payment?", True),
        (
            "If you deposit $1,000 at 6% compounded monthly for 5 years, how much will you have?",
            True,
        ),
        ("Mortgage $300k at 6.5% for 30 years. Calculate the monthly payment.", True),
        ("Car loan $25,000 at 7% for 5 years, find monthly payment", True),
    ],
)
def test_a_worked_problem_sets_out_its_values_before_it_asks(text: str, worked: bool) -> None:
    assert is_worked_problem(text) is worked


@pytest.mark.parametrize(
    ("text", "deposit"),
    [
        # Paid at the end of each month: the monthly deposit the savings formula pays in.
        (
            "If you deposit $200 at the end of each month at 6% compounded monthly for 5 "
            "years, how much will you have?",
            200,
        ),
        # Paid at a month's start it earns a month more, which no product works.
        (
            "If you deposit $200 at the beginning of each month at 6% compounded monthly for "
            "5 years, how much will you have?",
            None,
        ),
    ],
)
def test_a_deposit_paid_each_month_is_read_by_when_it_is_paid(
    text: str, deposit: float | None
) -> None:
    request = read_money_request(text)
    if deposit is None:
        assert request is None
    else:
        assert request is not None and request.values.get("deposit") == deposit
        assert "start" not in request.values


def test_a_recurring_deposit_read_as_one_sum_is_not_worked() -> None:
    # "Rs 10,000 in a recurring deposit" was worked as a lump sum.
    lump = "Rahul deposited Rs 10,000 in a recurring deposit at 7% for 3 years. Find the value."
    assert read_money_request(lump) is None
    monthly = read_money_request(
        "Rahul pays Rs 1,000 a month into a recurring deposit at 7% for 3 years. Find the value."
    )
    assert monthly is not None and monthly.values["deposit"] == 1000


def test_the_block_asks_a_worked_problem_for_its_working() -> None:
    request = read_money_request("A loan of $20,000 at 6% for 5 years. Find the monthly payment.")
    assert request is not None
    worked = work(request, None)
    lesson = money_block(request, worked, None, worked_problem=True)
    assert MONEY_WORKED_RULES in lesson and MONEY_REPLY_RULES not in lesson
    assert "**Formula**" in lesson and "never work out an intermediate value" in lesson
    plain = money_block(request, worked, None)
    assert MONEY_REPLY_RULES in plain and MONEY_WORKED_RULES not in plain
