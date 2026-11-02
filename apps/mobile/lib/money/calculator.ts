/**
 * The `calculator` fence (docs/money.md): a loan, a card payoff or savings, with a slider for
 * each input and readouts the server's formulas compute. This reads and checks the fence; the
 * card (`components/rich/CalculatorBlock.tsx`) draws it. A body that is not version 1, names an
 * unknown format, or carries a formula outside the closed language is refused whole, so a
 * half-understood card never shows.
 */

import { compileFormula, evaluateFormula, type Formula } from "@/lib/formula/tree";
import { isJsonRecord } from "@/lib/jsonFence";

const FORMATS = ["money", "percent", "years", "months", "number"] as const;
export type ValueFormat = (typeof FORMATS)[number];

const MAX_CONTROLS = 6;
const MAX_READOUTS = 6;
const NAME = /^[A-Za-z_][A-Za-z0-9_]{0,31}$/;
const KEY = /^money\.[a-z0-9_.]{1,64}$/;
const CURRENCY = /^[A-Z]{3}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** A reference value on a slider, such as today's average rate, with its date and source. */
type CalculatorMarker = {
  value: number;
  labelKey: string;
  asOf: string | null;
  source: string | null;
};

export type CalculatorControl = {
  name: string;
  labelKey: string;
  format: ValueFormat;
  min: number;
  max: number;
  step: number;
  /** The value the question asked about, inside min…max. */
  value: number;
  marker: CalculatorMarker | null;
};

type CalculatorReadout = {
  name: string;
  labelKey: string;
  format: ValueFormat;
  primary: boolean;
  /** Shown when the formula gives no number (a payment that never pays the card off). */
  neverKey: string | null;
  formula: Formula;
};

export type Calculator = {
  product: string;
  titleKey: string | null;
  currency: string | null;
  controls: CalculatorControl[];
  readouts: CalculatorReadout[];
};

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function key(value: unknown): string | null {
  return typeof value === "string" && KEY.test(value) ? value : null;
}

function format(value: unknown): ValueFormat | null {
  return typeof value === "string" && (FORMATS as readonly string[]).includes(value)
    ? (value as ValueFormat)
    : null;
}

function readMarker(raw: unknown): CalculatorMarker | null | undefined {
  if (raw === undefined || raw === null) return null;
  if (!isJsonRecord(raw) || !finite(raw.value)) return undefined;
  const labelKey = key(raw.label_key);
  if (!labelKey) return undefined;
  const asOf = typeof raw.as_of === "string" && DAY.test(raw.as_of) ? raw.as_of : null;
  const source =
    typeof raw.source === "string" && raw.source.trim() && raw.source.length <= 80
      ? raw.source.trim()
      : null;
  return { value: raw.value, labelKey, asOf, source };
}

function readControl(raw: unknown): CalculatorControl | null {
  if (!isJsonRecord(raw)) return null;
  const name = typeof raw.name === "string" && NAME.test(raw.name) && raw.name !== "pi" ? raw.name : null;
  const labelKey = key(raw.label_key);
  const kind = format(raw.format);
  const { min, max, step, value } = raw;
  if (!name || !labelKey || !kind) return null;
  if (!finite(min) || !finite(max) || !finite(step) || !finite(value)) return null;
  if (!(max > min) || !(step > 0) || step > max - min) return null;
  const marker = readMarker(raw.marker);
  if (marker === undefined) return null;
  return {
    name,
    labelKey,
    format: kind,
    min,
    max,
    step,
    value: Math.min(max, Math.max(min, value)),
    marker,
  };
}

function readReadout(raw: unknown, names: readonly string[]): CalculatorReadout | null {
  if (!isJsonRecord(raw)) return null;
  const name = typeof raw.name === "string" && NAME.test(raw.name) ? raw.name : null;
  const labelKey = key(raw.label_key);
  const kind = format(raw.format);
  const formula = compileFormula(raw.tree, names);
  if (!name || !labelKey || !kind || !formula) return null;
  if (raw.primary !== undefined && typeof raw.primary !== "boolean") return null;
  return {
    name,
    labelKey,
    format: kind,
    primary: raw.primary === true,
    neverKey: key(raw.never_key),
    formula,
  };
}

function unique(names: string[]): boolean {
  return new Set(names).size === names.length;
}

/** The calculator a fence body describes, or null when any part of it is not understood. */
export function parseCalculatorFence(content: string): Calculator | null {
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return null;
  }
  if (!isJsonRecord(raw) || raw.v !== 1) return null;
  if (!Array.isArray(raw.controls) || !Array.isArray(raw.readouts)) return null;
  if (raw.controls.length === 0 || raw.controls.length > MAX_CONTROLS) return null;
  if (raw.readouts.length === 0 || raw.readouts.length > MAX_READOUTS) return null;
  const controls = raw.controls.map(readControl);
  if (controls.some((control) => control === null)) return null;
  const okControls = controls as CalculatorControl[];
  const names = okControls.map((control) => control.name);
  if (!unique(names)) return null;
  const readouts = raw.readouts.map((readout) => readReadout(readout, names));
  if (readouts.some((readout) => readout === null)) return null;
  const okReadouts = readouts as CalculatorReadout[];
  if (!unique(okReadouts.map((readout) => readout.name))) return null;
  if (!okReadouts.some((readout) => readout.primary)) okReadouts[0] = { ...okReadouts[0]!, primary: true };
  return {
    product: typeof raw.product === "string" ? raw.product : "loan",
    titleKey: key(raw.title_key),
    currency: typeof raw.currency === "string" && CURRENCY.test(raw.currency) ? raw.currency : null,
    controls: okControls,
    readouts: okReadouts,
  };
}

/** The values the question asked about, by control name. */
export function askedValues(calculator: Calculator): Record<string, number> {
  return Object.fromEntries(calculator.controls.map((control) => [control.name, control.value]));
}

/** Each readout's number for these slider values; null when its formula gives none. */
export function readoutValues(
  calculator: Calculator,
  values: Readonly<Record<string, number>>,
): Record<string, number | null> {
  return Object.fromEntries(
    calculator.readouts.map((readout) => [readout.name, evaluateFormula(readout.formula, values)]),
  );
}
