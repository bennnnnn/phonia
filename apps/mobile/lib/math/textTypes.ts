/** Segment tree for native math text. */

export type MathAccentKind =
  | "overline"
  | "underline"
  | "hat"
  | "tilde"
  | "vec"
  | "vecLeft"
  | "bar"
  | "dot"
  | "ddot";

export type MathSegment =
  | { type: "text"; value: string }
  | { type: "upright"; value: string }
  | { type: "sup"; value: string; body?: MathSegment[] }
  | { type: "sub"; value: string; body?: MathSegment[] }
  | { type: "frac"; num: MathSegment[]; den: MathSegment[] }
  | { type: "sqrt"; body: MathSegment[]; degree?: string; index?: MathSegment[] }
  | { type: "cancel"; body: MathSegment[] }
  | { type: "accent"; kind: MathAccentKind; body: MathSegment[]; span?: boolean };
