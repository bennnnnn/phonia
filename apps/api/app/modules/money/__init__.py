"""Money: loans, card payoff and savings, worked by the server, with today's average rate.

The chat turn asks it through ``subject`` (``MoneyPeer``: prepare, prepare_standing, finish),
which the subject registry names beside the subjects; the rest stays inside the module. See
docs/money.md.
"""

# Money as the subject registry (services/subjects/registry) names it.
_MODULE_EXPORTS = ("subject",)
