/** Server-owned teaching pictures. The client draws the spec and does not recompute it. */

import { parseJsonRecord } from "@/lib/jsonFence";

export type TeachingSpec = {
  type: string;
  answer: string;
  speech: string;
  [key: string]: unknown;
};

const TYPES = new Set([
  "place_value",
  "number_bond",
  "ten_frame",
  "array",
  "number_line_move",
  "fraction_bar",
  "fraction_line",
  "decimal_compare",
  "rounding",
  "polynomial_division",
  "unit_circle",
  "box_plot",
  "frequency_table",
  "stem_leaf",
  "histogram",
  "scatter",
  "probability_tree",
  "transformation",
  "counting",
]);

export function parseTeaching(raw: string): TeachingSpec | null {
  const data = parseJsonRecord(raw);
  if (!data || typeof data.type !== "string" || !TYPES.has(data.type)) return null;
  if (typeof data.answer !== "string" || typeof data.speech !== "string" || !data.speech.trim()) {
    return null;
  }
  return data as TeachingSpec;
}

export function teachingSpeech(raw: string): string | null {
  return parseTeaching(raw)?.speech ?? null;
}
