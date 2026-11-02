/**
 * Naming a fence in a report, and why the phone refused one (`lib/sentry.ts`). A report
 * carries the fence's registry id, or the kind of block dispatch drew it as, and a reason
 * code: never the tag the reply wrote (it can be any text) and never the body.
 */
import type { FenceRenderKind } from "@/lib/fenceDispatch";
import type { FenceId } from "@/lib/fenceRegistry";
import { isJsonRecord, readJson } from "@/lib/jsonFence";

/** A fence as a report names it: its registry id, else the block it was drawn as (`code`, `html`). */
export type FenceReportName = FenceId | FenceRenderKind;

/** Why the phone did not draw a fence. */
export type FenceRefusal =
  /** The body had to be JSON and is not. */
  | "invalid_json"
  /** JSON naming a kind of picture this build does not draw. */
  | "unknown_kind"
  /** Read, but refused by the block's checks (a missing field, a value out of range, nothing to show). */
  | "invalid_spec"
  /** Valid, but the drawing failed (a chart's or a diagram's page reported an error). */
  | "draw_failed";

/** The name a report gives a fence dispatch decided on (`classifyFence`). */
export function fenceReportName(decision: { id?: FenceId; kind: FenceRenderKind }): FenceReportName {
  return decision.id ?? decision.kind;
}

/** What a block knows about its body's shape. */
type BodyShape = {
  /** The body must be JSON: one that does not parse is `invalid_json`. */
  json?: boolean;
  /** The field that names the body's kind, and every kind this build draws. */
  kinds?: { field: string; known: readonly string[] };
};

/** Why a body the block refused was refused, read from its shape alone. */
export function refusalOf(content: string, shape: BodyShape = {}): FenceRefusal {
  const read = readJson(content.trim());
  if (!read) return shape.json ? "invalid_json" : "invalid_spec";
  const kinds = shape.kinds;
  const kind = kinds && isJsonRecord(read.value) ? read.value[kinds.field] : undefined;
  if (kinds && typeof kind === "string" && !kinds.known.includes(kind)) return "unknown_kind";
  return "invalid_spec";
}
