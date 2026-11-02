"""Money: loans, card payoff and savings, with today's average rates (docs/money.md)."""

from pydantic import BaseModel


class MoneySettings(BaseModel):
    # Loan, card and savings questions get server-worked numbers and a calculator card.
    money_enabled: bool = True
    # Today's average rate is looked up on the web once per product, term and country,
    # and kept this long: averages move weekly at most.
    money_rate_cache_seconds: int = 43_200
    # A rate below the average divided by this, or above it times this, "is not realistic".
    money_unrealistic_ratio: float = 2.0
