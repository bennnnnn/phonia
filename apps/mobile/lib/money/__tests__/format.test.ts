import { formatCalculatorValue, formatPercent } from "@/lib/money/format";

const translate = (key: string, options?: Record<string, unknown>) => `${key}:${String(options?.count)}`;
const en = { locale: "en", currency: "USD", translate };

describe("formatCalculatorValue", () => {
  it("prints money with cents only when a small amount has them", () => {
    expect(formatCalculatorValue(964.9185613395013, "money", en)).toBe("$964.92");
    expect(formatCalculatorValue(300000, "money", en)).toBe("$300,000");
    expect(formatCalculatorValue(47370.68, "money", en)).toBe("$47,371");
    expect(formatCalculatorValue(500, "money", en)).toBe("$500");
  });

  it("uses the app's language and the fence's currency", () => {
    const euros = formatCalculatorValue(1851.06, "money", { ...en, locale: "de", currency: "EUR" });
    expect(euros.replace(/\s/g, " ")).toBe("1.851,06 €");
  });

  it("prints a plain number when the fence names no currency", () => {
    expect(formatCalculatorValue(1851.06, "money", { ...en, currency: null })).toBe("1,851.06");
  });

  it("falls back to the code when the currency is unknown to Intl", () => {
    expect(formatCalculatorValue(12.5, "money", { ...en, currency: "ZZZ" })).toMatch(/12\.50/);
  });

  it("prints a rate as a percent with at most two decimals", () => {
    expect(formatCalculatorValue(6.27, "percent", en)).toBe("6.27%");
    expect(formatCalculatorValue(1, "percent", en)).toBe("1%");
    expect(formatPercent(6.275, "fr")).toMatch(/^6,28\s?%$/);
  });

  it("counts years and months, a last part-month as a month", () => {
    expect(formatCalculatorValue(30, "years", en)).toBe("money.years_count:30");
    expect(formatCalculatorValue(34.23, "months", en)).toBe("money.months_count:35");
    expect(formatCalculatorValue(12, "months", en)).toBe("money.months_count:12");
  });
});
