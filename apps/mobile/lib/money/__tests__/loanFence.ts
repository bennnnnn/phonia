/** A mortgage calculator fence as the server writes it (docs/money.md), for the tests. */

type Tree = Record<string, unknown>;

const n = (value: number): Tree => ({ n: value });
const v = (name: string): Tree => ({ v: name });
const op = (name: string, ...a: Tree[]): Tree => ({ op: name, a });

const rate = op("/", v("rate"), n(1200));
const months = op("*", v("years"), n(12));
const payment = {
  op: "if",
  a: [
    { cmp: ">", a: [v("rate"), n(0)] },
    op("/", op("*", v("amount"), rate), op("-", n(1), op("^", op("+", n(1), rate), op("neg", months)))),
    op("/", v("amount"), months),
  ],
};
const total = op("*", payment, months);

export function loanFence(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    v: 1,
    product: "loan",
    title_key: "money.title.mortgage",
    currency: "USD",
    controls: [
      { name: "amount", label_key: "money.amount", format: "money", min: 50000, max: 1000000, step: 5000, value: 300000 },
      {
        name: "rate",
        label_key: "money.rate",
        format: "percent",
        min: 0,
        max: 15,
        step: 0.05,
        value: 1,
        marker: { value: 6.27, label_key: "money.average", as_of: "2026-10-16", source: "Freddie Mac via FRED" },
      },
      { name: "years", label_key: "money.term_years", format: "years", min: 1, max: 40, step: 1, value: 30 },
    ],
    readouts: [
      { name: "payment", label_key: "money.monthly_payment", format: "money", primary: true, tree: payment },
      { name: "interest", label_key: "money.total_interest", format: "money", tree: op("-", total, v("amount")) },
      { name: "total", label_key: "money.total_paid", format: "money", tree: total },
    ],
    ...overrides,
  };
}

/** A card payoff whose months never end when the payment is below the interest. */
export function cardFence(payment: number): Record<string, unknown> {
  const monthly = op("/", v("apr"), n(1200));
  const months = {
    op: "if",
    a: [
      { cmp: ">", a: [v("payment"), op("*", v("balance"), monthly)] },
      op(
        "/",
        op("neg", { fn: "log", a: [op("-", n(1), op("/", op("*", monthly, v("balance")), v("payment")))] }),
        { fn: "log", a: [op("+", n(1), monthly)] },
      ),
      op("/", n(1), n(0)),
    ],
  };
  return {
    v: 1,
    product: "card_payoff",
    title_key: "money.title.card",
    currency: "USD",
    controls: [
      { name: "balance", label_key: "money.balance", format: "money", min: 500, max: 50000, step: 100, value: 5000 },
      { name: "apr", label_key: "money.apr", format: "percent", min: 0, max: 36, step: 0.1, value: 24 },
      { name: "payment", label_key: "money.monthly_payment", format: "money", min: 25, max: 2000, step: 5, value: payment },
    ],
    readouts: [
      {
        name: "months",
        label_key: "money.months_to_payoff",
        format: "months",
        primary: true,
        never_key: "money.never",
        tree: months,
      },
    ],
  };
}
