import { askedValues, parseCalculatorFence, readoutValues } from "@/lib/money/calculator";
import { cardFence, loanFence } from "@/lib/money/__tests__/loanFence";

const parse = (body: unknown) => parseCalculatorFence(JSON.stringify(body));

describe("parseCalculatorFence", () => {
  it("reads the contract's mortgage card", () => {
    const calculator = parse(loanFence());
    expect(calculator).not.toBeNull();
    expect(calculator!.titleKey).toBe("money.title.mortgage");
    expect(calculator!.currency).toBe("USD");
    expect(calculator!.controls.map((control) => control.name)).toEqual(["amount", "rate", "years"]);
    expect(calculator!.controls[1]!.marker).toEqual({
      value: 6.27,
      labelKey: "money.average",
      asOf: "2026-10-16",
      source: "Freddie Mac via FRED",
    });
    expect(calculator!.readouts.map((readout) => readout.primary)).toEqual([true, false, false]);
  });

  it("computes each readout from the slider values", () => {
    const calculator = parse(loanFence())!;
    const asked = readoutValues(calculator, askedValues(calculator));
    expect(asked.payment).toBeCloseTo(964.92, 2);
    expect(asked.total).toBeCloseTo(964.9185613395013 * 360, 6);
    expect(asked.interest).toBeCloseTo(964.9185613395013 * 360 - 300000, 6);
    const average = readoutValues(calculator, { amount: 300000, rate: 6.27, years: 30 });
    expect(average.payment).toBeCloseTo(1851.06, 2);
    const free = readoutValues(calculator, { amount: 30000, rate: 0, years: 5 });
    expect(free.payment).toBe(500);
  });

  it("gives no number for a card payment that never pays it off", () => {
    const never = parse(cardFence(100))!;
    expect(readoutValues(never, askedValues(never)).months).toBeNull();
    const pays = parse(cardFence(200))!;
    expect(readoutValues(pays, askedValues(pays)).months).toBeGreaterThan(30);
  });

  it("makes the first readout primary when none says so", () => {
    const body = loanFence();
    const readouts = (body.readouts as Record<string, unknown>[]).map(({ primary: _primary, ...rest }) => rest);
    expect(parse({ ...body, readouts })!.readouts[0]!.primary).toBe(true);
  });

  it("keeps the asked value inside the slider's range", () => {
    const body = loanFence();
    const controls = body.controls as Record<string, unknown>[];
    controls[0] = { ...controls[0], value: 5_000_000 };
    expect(parse(body)!.controls[0]!.value).toBe(1_000_000);
  });

  it("drops a date or a source it cannot read, but keeps the marker", () => {
    const body = loanFence();
    const controls = body.controls as Record<string, unknown>[];
    controls[1] = { ...controls[1], marker: { value: 6.27, label_key: "money.average", as_of: "Oct 16", source: "" } };
    expect(parse(body)!.controls[1]!.marker).toEqual({
      value: 6.27,
      labelKey: "money.average",
      asOf: null,
      source: null,
    });
  });

  const broken: [string, (body: Record<string, unknown>) => unknown][] = [
    ["not JSON", () => "{not json"],
    ["another version", (body) => ({ ...body, v: 2 })],
    ["no controls", (body) => ({ ...body, controls: [] })],
    ["no readouts", (body) => ({ ...body, readouts: [] })],
    [
      "an unknown format",
      (body) => ({
        ...body,
        controls: [{ ...(body.controls as object[])[0], format: "bitcoin" }, ...(body.controls as object[]).slice(1)],
      }),
    ],
    [
      "a range with no width",
      (body) => ({
        ...body,
        controls: [{ ...(body.controls as object[])[0], min: 5, max: 5 }, ...(body.controls as object[]).slice(1)],
      }),
    ],
    [
      "a label that is not a money key",
      (body) => ({
        ...body,
        controls: [{ ...(body.controls as object[])[0], label_key: "Loan amount" }, ...(body.controls as object[]).slice(1)],
      }),
    ],
    [
      "two controls with one name",
      (body) => ({ ...body, controls: [(body.controls as object[])[0], (body.controls as object[])[0]] }),
    ],
    [
      "a formula naming a value no slider sets",
      (body) => ({
        ...body,
        readouts: [{ name: "x", label_key: "money.total_paid", format: "money", tree: { v: "price" } }],
      }),
    ],
    [
      "a formula as text",
      (body) => ({
        ...body,
        readouts: [{ name: "x", label_key: "money.total_paid", format: "money", tree: "amount * 2" }],
      }),
    ],
    [
      "a marker with no label",
      (body) => {
        const controls = [...(body.controls as Record<string, unknown>[])];
        controls[1] = { ...controls[1], marker: { value: 6.27 } };
        return { ...body, controls };
      },
    ],
  ];

  it.each(broken)("refuses %s", (_label, change) => {
    const body = change(loanFence());
    expect(parseCalculatorFence(typeof body === "string" ? body : JSON.stringify(body))).toBeNull();
  });
});
