/**
 * Shared type roles — prefer these over one-off 13/14/15/16 mixes for the
 * same visual job. Colors stay on theme tokens; this file owns size/weight.
 *
 * Dynamic Type: roles keep the platform default (`allowFontScaling`), so
 * body copy follows the reader. Math layout has its own scale. A control
 * that shares a line with a 44pt target (the composer field) sets
 * `maxFontSizeMultiplier` to `DYNAMIC_TYPE_MAX` so a very large size does
 * not clip the caret or the send button. Digits in a fixed box (the pickers)
 * stop sooner, at `DYNAMIC_TYPE_PICKER_MAX`.
 */
import type { TextStyle } from "react-native";

import { UI_FONT, uiFontFamily } from "@/lib/uiFont";

/** Cap for a control that shares a line with a 44pt target. Body copy stays uncapped. */
export const DYNAMIC_TYPE_MAX = 1.5;

/**
 * Cap for digits in a fixed box: the time picker's readout, the clock dial's
 * numbers, the calendar's days and years. Their boxes are sized for this.
 */
export const DYNAMIC_TYPE_PICKER_MAX = 1.3;

function face(weight: "400" | "500" | "600" | "700"): Pick<TextStyle, "fontFamily" | "fontWeight"> {
  return {
    fontFamily: uiFontFamily(weight),
    // The file is already this weight. Android registers it as the regular
    // face; a 700 weight looks up a bold slot that was never loaded and draws
    // Roboto. iOS would faux-bold that same file. Ask both for the regular slot.
    fontWeight: "400",
  };
}

export const Type = {
  /** Primary body copy. Multiline roles use the platform's scaled line box. */
  body: {
    fontSize: 16,
    ...face("400"),
  },
  /** Secondary body / supporting paragraphs */
  secondary: {
    fontSize: 14,
    ...face("400"),
  },
  /** Captions / compact meta */
  caption: {
    fontSize: 12,
    ...face("500"),
  },
  /** 12pt regular meta — timestamps, domain lines, "PDF" kind labels.
   *  No lineHeight (matches caption/label: single-line roles omit it). */
  meta: {
    fontSize: 12,
    ...face("400"),
  },
  /** 11pt uppercase tracked overline — drawer/home section dividers.
   *  No lineHeight (single-line role). */
  overline: {
    fontSize: 11,
    ...face("700"),
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  /** 11pt bold, untracked — counts and tags inside a badge. The overline's
   *  size without its uppercase tracking. */
  micro: {
    fontSize: 11,
    ...face("700"),
  },
  /** 13pt compact chrome — banners, inline alerts, supporting meta that
   *  sat between caption (12) and secondary (14). Override weight at the site. */
  compact: {
    fontSize: 13,
    ...face("400"),
  },
  /** Compact control labels */
  label: {
    fontSize: 14,
    ...face("600"),
  },
  /** 15pt callout — toasts and dense card titles between body (16) and
   *  secondary (14). */
  callout: {
    fontSize: 15,
    ...face("600"),
  },
  /** Screen / section titles */
  title: {
    fontSize: 20,
    ...face("600"),
  },
  /** Nav bar & sheet titles — the 17pt role the scale was missing (8+ sites
   *  invented it as `...Type.title, fontSize: 17` or a bare 17/700). */
  navTitle: {
    fontSize: 17,
    ...face("600"),
  },
  /** Onboarding / marketing display. Tightened: 28pt bold reads loose at 0. */
  display: {
    fontSize: 28,
    ...face("700"),
    letterSpacing: -0.5,
  },
  /** Large clock numerals (time picker header). Tabular so digits don't jiggle. */
  clock: {
    fontSize: 56,
    ...face("400"),
    fontVariant: ["tabular-nums"],
  },
  /** Markdown heading ladder (h1–h6). Wrapped headings keep scaled line boxes. */
  h1: { fontSize: 22, ...face("700") },
  h2: { fontSize: 19, ...face("700") },
  h3: { fontSize: 17, ...face("700") },
  /** Section label — never smaller than body, or hierarchy inverts. */
  h4: { fontSize: 16, ...face("700") },
  h5: { fontSize: 16, ...face("700") },
  h6: { fontSize: 16, ...face("700") },
} as const satisfies Record<string, TextStyle>;

/**
 * Weight changes on top of a role: `{ ...Type.body, ...Weight.bold }`.
 * Each entry sets the matching Source Sans 3 file and asks for the regular
 * slot. A 700 weight makes Android drop the file and draw Roboto. Lint bans
 * raw `fontWeight`; use this instead.
 */
export const Weight = {
  regular: face("400"),
  medium: face("500"),
  semibold: face("600"),
  bold: face("700"),
} as const satisfies Record<string, TextStyle>;

/**
 * Italic on top of a role: `{ ...Type.body, ...Italic.regular }`. Each entry is
 * a real italic file; `fontStyle: "italic"` on these one-file families draws
 * upright on iOS and Roboto Italic on Android, so it is never set.
 */
export const Italic = {
  regular: { fontFamily: UI_FONT.italic, fontWeight: "400", fontStyle: "normal" },
  semibold: { fontFamily: UI_FONT.semiboldItalic, fontWeight: "400", fontStyle: "normal" },
  bold: { fontFamily: UI_FONT.boldItalic, fontWeight: "400", fontStyle: "normal" },
} as const satisfies Record<string, TextStyle>;
