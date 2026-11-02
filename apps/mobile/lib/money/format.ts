/**
 * How a calculator value reads in the app's language: money in the fence's currency, a rate
 * as a percent, a term in years or months, a date as "Oct 16".
 */

import type { ValueFormat } from "@/lib/money/calculator";

type Translate = (key: string, options?: Record<string, unknown>) => string;

type FormatContext = {
  /** The app's language ("en", "de"); Intl falls back to English when it has no data. */
  locale: string;
  /** ISO 4217 code, or null to print a plain number. */
  currency: string | null;
  translate: Translate;
};

function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  try {
    return new Intl.NumberFormat(locale, options);
  } catch {
    return new Intl.NumberFormat("en", options);
  }
}

/** Cents for a small amount that has them ($964.92); whole units otherwise ($300,000). */
function moneyDigits(value: number): number {
  const whole = Math.abs(value - Math.round(value)) < 0.005;
  return whole || Math.abs(value) >= 10_000 ? 0 : 2;
}

function money(value: number, { locale, currency }: FormatContext): string {
  const digits = moneyDigits(value);
  const options = { minimumFractionDigits: digits, maximumFractionDigits: digits };
  if (!currency) return numberFormat(locale, options).format(value);
  try {
    return numberFormat(locale, { ...options, style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${numberFormat(locale, options).format(value)}`;
  }
}

/** A rate as written, at most two decimals: "6.27%", "1%". */
export function formatPercent(value: number, locale: string): string {
  return numberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(value / 100);
}

/** One value as the card shows it. */
export function formatCalculatorValue(
  value: number,
  kind: ValueFormat,
  context: FormatContext,
): string {
  switch (kind) {
    case "money":
      return money(value, context);
    case "percent":
      return formatPercent(value, context.locale);
    case "years": {
      const count = Math.round(value * 10) / 10;
      return context.translate("money.years_count", { count });
    }
    case "months": {
      // A last part-month is still a month to pay.
      const count = Math.max(0, Math.ceil(value - 1e-9));
      return context.translate("money.months_count", { count });
    }
    case "number":
      return numberFormat(context.locale, { maximumFractionDigits: 2 }).format(value);
  }
}
