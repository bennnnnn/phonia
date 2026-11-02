# Money: loans, cards, savings and live rates

"What is my mortgage for a $300k house at 1%?" gets a worked answer, a card with sliders for
the amount, the rate and the term, and a note that compares the rate with today's average:

> **Note:** 1% is not a realistic 30-year fixed mortgage rate. As of Oct 16, 2026, the average
> in the United States is 6.27% ([Mortgage Rates - Freddie Mac](https://www.freddiemac.com/pmms)).

The reply's numbers are the server's, never the model's arithmetic. The phone redraws the card
as a slider moves by **evaluating** the formula the server sent; it never solves anything.

## Where it lives

| Part | Path |
|------|------|
| Products, formulas, defaults, slider ranges (data, not code paths) | `apps/api/app/modules/money/catalog.py` |
| Reading a request (product, amount, rate, term, payment, currency, country) | `apps/api/app/modules/money/read.py`; the kind (a used car), `kinds.py` |
| A what-if that changes the chat's last request ("what if i only do 3 years instead") | `apps/api/app/modules/money/follow_up.py`, its grammar `change_line.py` |
| A loan told over two lines ("I am planning to buy a car", then "20k with 6 percent") | `apps/api/app/modules/money/purchase.py`; what each loan buys, `Product.goods` |
| The card's currency and the country a rate search names | `apps/api/app/modules/money/currencies.py` |
| Numbers for the asked values, the prompt block and the note | `apps/api/app/modules/money/solve.py`, `block.py`, `note.py` |
| Today's average rate: one web search, one checked structured read, cached | `apps/api/app/modules/money/rates.py` |
| The calculator fence and its self-check | `apps/api/app/modules/money/fence.py`, `schemas.py` |
| The turn: prepare beside the prompt, finish after the stream | `apps/api/app/modules/money/service.py` (chat asks it through `money/subject.py`, the registry's `MONEY`), `apps/api/app/modules/chat/turn_prep/money.py`, `apps/api/app/modules/chat/finalize_money.py` |
| Settings (`money_enabled`, `money_rate_cache_seconds`, `money_unrealistic_ratio`) | `apps/api/app/core/settings/money.py` |
| The checked formula tree (shared with physics) | `apps/api/app/services/law_binding/expression.py` (`to_tree`) |
| The card | `apps/mobile/components/rich/CalculatorBlock.tsx` |
| The evaluator twin | `apps/mobile/lib/formula/tree.ts` |
| The slider | `apps/mobile/ui/controls/Slider.tsx` |

## Products are data

A product is one catalog row: its inputs (each with a unit, a default and a range rule), its
outputs (each a formula over the inputs), the words that name it, and how to look up its
average rate today (`RateLookup`: what the rate is called, the terms averages are published for,
the plausible range and how recent a figure must be). Adding a product is one row; nothing else
branches on its name. A kind of a product priced apart is a `Variant` on its row, with its own
words and `RateLookup`: "a used car for 14000" (also pre-owned, certified pre-owned,
second-hand) is a car loan looked up at the used-car average, cached apart from the new-car one
and named in the reply ("used car loan rate"; used-car averages are published for every term at
once, so that lookup names none). The kind counts only in two fixed phrases about the vehicle
being bought: "buying a used car" (also buy, financing, finance, getting, get, purchasing,
purchase, thinking of buying, looking at; pre-owned, second-hand, certified pre-owned; car,
truck, SUV, vehicle) and "a loan for a used car", and never after "or", "vs", "instead of",
"than", "rather", "not", "sold", "selling" or "paid off" anywhere earlier in the message (that
used car is the alternative or another one). Missing a used car is the safe direction: the
reply then uses the new-car average and says so. New or no kind said is the row's own lookup.

The row's own lookup starts beside a variant's. When the variant's finds nothing in time, the
row's own average stands in and says so: the reply and the note name it ("today's average
60-month new car loan rate") and add the variant's `stand_in` words ("No used-car average was
found; used-car loans usually cost more."), the model is told never to call it a used-car rate,
and a rate the user gave is not called unrealistic beside it. The first live used-car ask found
no used-car average and got no numbers at all, where the new-car average had worked it. Version
1 rows:

- **Loan** (mortgage, car, personal, student, any other amortised loan): amount, annual rate,
  term → monthly payment, total interest, total paid. A rate of 0% pays amount ÷ months.
- **Card payoff**: balance, APR, monthly payment → months to pay off, total interest. A payment
  at or below the first month's interest never pays it off, and the card says so.
- **Savings**: starting amount, monthly deposit, annual rate, years → final balance, total
  deposited, interest earned. Interest compounds as often as the request says ("compounded
  quarterly", "with semi-annual compounding", "compounded daily"): a setting of the row
  (`Product.settings`, `per_year`), not a slider, written into the card's trees as a number
  (`Product.outputs_at`), monthly when it says none, and the block names it so the reply
  does. A start grows (1 + rate/n)^(n·years); a deposit made each month grows by the month's
  share of that. Each compounding word is read with what follows it ("compounded per
  quarter", "on a quarterly basis") or the one word before it ("semi annual compounding");
  spaces and hyphens are one. Any compounding word whose frequency isn't read so
  ("continuously", "compounded and paid quarterly", a bare "compounded"), two that disagree,
  or a loan compounded other than monthly is left to the model, never worked as monthly; a
  card's APR is charged by the month however it compounds (`compounding.py`; live
  2026-10-31, "compounded quarterly" was worked monthly).
- **Investing** (invest, investing, investment, retirement): the same inputs and results as
  savings, with no average looked up: a market's return has no bank average to judge it by.

**One value per slot.** A request is worked only from what it says once, read whole: one
sum for each input, one rate, one term, one money down, one compounding. Two rates or two
terms (a comparison, a refinance, "15 or 30 years"), two sums for one input, a sum the reader
cannot read whole ("5 lakh", "1.2 billion"; digits are read in every grouping: "250,000.50",
"250.000,50", "5,00,000"; a rate's decimal comma is its decimal point, "3,5%" is 3.5%, and
"3,125%" could be either, so it is not read), a deposit paid each week, or a compounding word it cannot read
give no worked numbers and no card: the model answers. "N% down" is always the share of the
price put down, never the rate; a plan's name ("401k", "529 plan") is no sum; interest said
to be simple ("if interest is simple", "no compounding", "I = PRT") is left to maths.

A term the user didn't give comes from the row's default (a 30-year mortgage, a 5-year car loan),
and the reply says it assumed one. A term in words is read as in digits ("seven years",
"twenty-five years", "two and a half years", "one hundred twenty months"), by the first ask, the follow-up grammar and the
two-line loan alike (`phrases.py`). A length of time that is no term is left out: an age, time
gone by or a gap ("thirty years old", "ten years ago", "five years apart", "been paying for
three years", "twelve months of payments", "the past 2 years", and any "for N years" in a
clause about time already spent paying or holding a loan: "I've been paying my mortgage at
4% for five years", "we've had our loan for 5 years"; looking at, thinking about or saving
for a new loan keeps its term). A currency named before its sum ("Birr 3,000", "USD 500")
marks it as money; an exchange rate ("USD 1 = ETB 57", "57 birr to the dollar"), a note or
coin ("Birr 500 notes") and the same sum said again ("that's about USD 21,600") are no sum
(`sums.py`).

Which sum is the loan (`loan_sums.py`; live 2026-10-31, a house that "costs Birr 250,000" with
"Birr 50,000 which he will use as a deposit" was worked as a 250,000 loan):

- A sum said to be borrowed or owed ("borrow 20k", "still owe 20k") is the loan as it stands;
  money put down came off it already.
- Otherwise the price less the sum put down, said as a down payment or a deposit, also in a
  clause after it ("which he will use as a deposit"; not a deposit with a landlord, a bank or
  a booking), or as paid toward it when "the rest" is borrowed ("she pays $5,000 and borrows
  the rest").
- One sum named as the loan ("a $15,000 car loan", "a 300k mortgage") beside others is the loan.
- Two sums, one said to be a price and none borrowed or named a loan ("costs 250,000 and I have
  50,000 saved", "the difference between a $300,000 house and a $350,000 house"), name no loan,
  and none is assumed: the model answers. An income ("my salary is $90,000", "I make 80k a
  year") is never a candidate. A rate they didn't give comes from today's average when there
is one; otherwise the model asks for it.

## Follow-ups

"hmm what if i only do 3 years instead" right after a money reply is that request with the term
changed, and the server works it and sends the card exactly as for a first ask. The follow-up
chips under a money reply ask exactly this; before, the model did the arithmetic itself and was
off by dollars (live 2026-10-25: $340.58 a month for $340.45).

- The server works two changes only, both common and safe: a new term ("3 years", "36 months",
  "over 4 years", "a 15 year mortgage", "make it 4 years", "pay it off in 2 years") and a new
  rate with its words ("at 6%", "6% apr", "6% interest", "the rate is 6%", "a 6% rate"). The line
  must ask for the change: it opens (after "hmm", "ok", "so") with "what if", "what about", "how
  about", "and", "or", "make it", "try", "do", "go with" or "i only do", or ends with "instead"
  or "instead of N". Every other change (a price or amount, a down payment, a card payment or
  balance, a savings deposit or start, used or new) and every other line ("36 months?", "7%",
  "is it 6%?") goes to the model, as before. Four reviews (2026-10-25) of wider readers each
  found new shapes they misread, and a misread follow-up is a wrong number the reply calls the
  answer: a model year as a price, a card payment ("my payment is 3%") as the APR, "it's 40k
  miles" as a $40,000 loan, "it's been 5 years" as a 5-year mortgage.
- The line is read by a positive grammar (`change_line.py`): every word must belong to the frame,
  a term or rate phrase, or a short filler list. Any other word ("miles", "payment", "make",
  "been", "then", "from", "left") means no follow-up. "6% for 10 years" without "at" is a rate
  for a while, "at 5 years" and "in 2 years" are points in time, "interest only" is another kind
  of loan, and a line about the person ("what if I'm 30 years") changes nothing.
- The new value must lie on the slider the request's last card had (`fence.slider_range`): a
  mortgage runs 5 to 40 years, so "2 years" is no new term.
- The turn passes the user's earlier lines and the last reply (`turn_prep/money.py`), each
  line in the parts its own turn read it in (a multi-part line's plan, read in the pool with the
  message), so "set a reminder for 9 tomorrow and what's the payment on a 20000 car loan at 6%"
  is the 20000 loan, not one of 9. A line the pool did not plan (one with no text) ends the run;
  it is never planned on the event loop. The request a line changes is the last one in the user's
  last three lines, and every line after it must be a change of it too; a line about something
  else, or a change the server left to the model, ends the run.
- The follow-up's average is read again for its own kind and term. When that is not the rate
  the last reply's card showed (a stand-in the first time, the used-car average now), the
  block says the rate changed and why.
- The money block tells the model which inputs changed and that the numbers below are the
  answer, never to be redone from the earlier reply.

## A loan told over two lines

"I am planing to buy a car", a reply asking new or used and the budget, then "20k with 6
percent" is a car loan of 20,000 at 6%, worked by the server with its card. Neither line is a
request on its own, so before (live 2026-10-25) the model did the sums and was off ($1,930
interest where 20k at 6% over 36 months is $1,904). Both lines are read by a positive grammar
(`purchase.py`); any word outside it leaves the line to the model, as before.

- The user's line before says only that they are buying what a loan product finances, its
  `goods` (a car, truck, SUV or vehicle; a house, home or condo): "I am planning to buy a
  car", "we want to buy a used car", "buying a house for 400k", "House buying for 400k", "I'm
  getting a 30k truck next month". Not "I bought a car last week", "buy a house in minecraft",
  "buying a car for my son" or a line that also asks something. A used car there is the
  used-car loan, as in one line.
- With no price there, this line is only an amount and a rate ("with", "at"), and maybe a term:
  "20k with 6 percent", "$20,000 at 6% apr", "20k at 6% for 3 years". The amount is the loan's,
  as "car loan 20k at 6%" reads in one line. "20k steps with 6 percent incline", "my car does
  20k miles a year", "20k with 6 percent growth for 3 years" and a salary line are not.
- With a price there, a bare amount is not certain: "60k at 6 percent", after the reply asked
  for the down payment and the rate, may be either, so it goes to the model. Only an amount
  said to be down is read ("60k down at 6 percent", "with 60k down", "down payment of 60k at
  6%"), and the loan is the price less it. The reply's question is not read to decide.
- A down payment after a line with no price ("Down payment 3k" after "20k with 6 percent")
  goes to the model: whether the 20k was the price or the loan was never said.
- A what-if after the loan ("what if 3 years instead") changes it like any other request.

## Today's rates

`rates.py` looks up today's average with one web search through the web-search module's own
cached search, for example "average 30-year fixed mortgage rate this week the United States".
One small structured read (`ROUTING.background`, validated by `RateReading`) takes the rate, the
date it describes and the URL that states it from the top results. The reading counts only when:

- the rate lies in the product's plausible range (`RateLookup.plausible`);
- the date parses and is no older than the row's `fresh_days` (and not in the future);
- the URL is one of the pages the search returned.

Anything else is no average. One answer serves every turn for the same product, term bucket
and country for `money_rate_cache_seconds`, so most turns never search. A miss spends one of the
asking user's daily searches.

The country comes from the request's currency (birr → Ethiopia), else the user's saved place,
else the United States; the query carries it, so every country takes the same path.

The lookup starts with the turn. It is waited on before the prompt only when the numbers need it
(no rate given, or "what are rates now?"), for at most a few seconds; otherwise it runs while the
reply streams and the finalize pass collects it. No average means no note and no marker; the
model is told never to state a market rate itself, and a rates question without one says it
could not find today's figure.

The note compares the user's rate with the average. A rate below `average ÷ ratio` or above
`average × ratio` (`money_unrealistic_ratio`, default 2) "is not realistic"; any other gets
"for reference"; a rate taken from the average says so. The server writes the note, with the
average's date and a link to its source.

## The `calculator` fence

The server appends it after the reply; the model never writes one. JSON, one object:

```json
{
  "v": 1,
  "product": "loan",
  "title_key": "money.title.mortgage",
  "currency": "USD",
  "controls": [
    {"name": "amount", "label_key": "money.amount", "format": "money",
     "min": 50000, "max": 1000000, "step": 5000, "value": 300000},
    {"name": "rate", "label_key": "money.rate", "format": "percent",
     "min": 0, "max": 15, "step": 0.05, "value": 1,
     "marker": {"value": 6.27, "label_key": "money.average", "as_of": "2026-10-16",
                "source": "Mortgage Rates - Freddie Mac",
                "source_url": "https://www.freddiemac.com/pmms"}},
    {"name": "years", "label_key": "money.term_years", "format": "years",
     "min": 1, "max": 40, "step": 1, "value": 30}
  ],
  "readouts": [
    {"name": "payment", "label_key": "money.monthly_payment", "format": "money",
     "primary": true, "tree": {"op": "...", "a": []}},
    {"name": "interest", "label_key": "money.total_interest", "format": "money", "tree": {}},
    {"name": "total", "label_key": "money.total_paid", "format": "money", "tree": {}}
  ]
}
```

- `format` is a closed list: `money`, `percent`, `years`, `months`, `number`.
- Each readout's `tree` is over the control names only. A value that is not finite (a card
  payment that never pays off) shows the readout's `never_key` text, or a dash.
- `marker` is optional: today's average on the rate slider, with its date, the source's title
  and, optionally, `source_url` (the page the rate came from).
- `currency` is the one the request named, else the user's saved place's, else USD when no
  place is saved (`currencies.currency_for`). It is "" only for a saved place the list does not
  know; the phone then shows plain numbers, no symbol.
- Labels are i18n keys the phone translates; there is no English text in the fence.
- The server checks every tree before sending: only the closed operations and declared names,
  finite at the asked values and at every corner of the control ranges where the formula is
  defined, and equal to the server's own numbers at the asked values. A card that fails is not
  sent; the reply still has its worked numbers.

## Label keys

The fence names text by key, and the phone translates it in all nine languages. Every key starts
with `money.`; the phone refuses a fence whose `title_key` or `label_key` doesn't, and shows a
fallback (the title "Loan", an empty label, a dash) for a `money.` key it has no text for, never
the raw key. Keys the phone has (a server test, `test_money_label_keys.py`, holds the catalog to them):

| Use | Keys |
|-----|------|
| `title_key` | `money.title.mortgage`, `money.title.car`, `money.title.personal`, `money.title.student`, `money.title.loan`, `money.title.card`, `money.title.savings`, `money.title.investing` |
| control `label_key` | `money.amount`, `money.rate`, `money.term_years`, `money.term_months`, `money.balance`, `money.apr`, `money.payment`, `money.start`, `money.deposit` |
| readout `label_key` | `money.monthly_payment`, `money.total_interest`, `money.total_paid`, `money.months_to_payoff`, `money.final_balance`, `money.total_deposited`, `money.interest_earned` |
| readout `never_key` | `money.never` ("Never at this payment") |
| marker `label_key` | `money.average` ("Avg {{value}} · {{date}}"); with no `as_of` the phone uses `money.average_undated` |

The phone's own keys, not sent by the server: `money.average_a11y`, `money.average_a11y_undated`,
`money.source`, `money.source_undated` (the line under the card naming the marker's source and
date), `money.reset`, `money.reset_a11y`, and the counted `money.years_count` / `money.months_count`
that print a `years` or `months` value ("30 years"; a `months` readout counts a last part-month).

On the phone: the card is `components/rich/CalculatorBlock.tsx`, its reader `lib/money/calculator.ts`,
its formatting `lib/money/format.ts` (money in the fence's `currency` and the app's language, cents
only on amounts under 10,000 that have them). Tapping the marker sets the slider to the marker's
exact value. Where the user left the sliders survives the list recycling the card and is cleared at
sign-out. Copy and Read aloud leave the card out: the reply's own text states its numbers.

Control names per product: mortgage `amount, rate, years`; car `amount, rate, months`; student `amount, rate, years`; personal `amount, rate, months`; loan `amount, rate, years`; card `balance, apr, payment`; savings and investing `start, deposit, rate, years`. A car or personal loan's term is `months`; every other term is `years`.

## The formula tree

The same closed language the catalog's expressions use (`expression.py`), as JSON, never as
text:

| Node | JSON |
|------|------|
| number | `{"n": 0.05}` |
| name (a control, or `pi`) | `{"v": "rate"}` |
| `+ - * / ^` | `{"op": "+", "a": [left, right]}` |
| unary minus | `{"op": "neg", "a": [x]}` |
| function (`sqrt sin cos tan asin acos atan exp log abs`) | `{"fn": "log", "a": [x]}` |
| condition | `{"op": "if", "a": [{"cmp": ">", "a": [left, right]}, then, else]}` |

`cmp` is one of `> >= < <= ==`. Division by zero, a negative base to a fractional power or a
function outside its domain gives no number (the phone shows a dash). Depth is at most 32 and a
tree at most 512 nodes.

`docs/fixtures/formula_tree_cases.json` holds trees, values and the server's result; the phone's
jest test evaluates each and must agree to 1e-9 relative (`null` means no number). The server
test that writes it runs with `UPDATE_FORMULA_TREE_FIXTURE=1`.
