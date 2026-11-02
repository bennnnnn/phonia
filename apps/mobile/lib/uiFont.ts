/** One line of the UI face, in em: hhea ascender 1024 + descender 400 per 1000 units, no gap. */
export const UI_LINE_EM = 1.424;

/** Source Sans 3, one file per weight. Loaded in the root layout. Not Inter. */
export const UI_FONT = {
  regular: "SourceSans3",
  medium: "SourceSans3-Medium",
  semibold: "SourceSans3-Semibold",
  bold: "SourceSans3-Bold",
  /** True italic files: `fontStyle: "italic"` on a one-file family draws upright
   *  on iOS and Roboto Italic on Android. */
  italic: "SourceSans3-Italic",
  semiboldItalic: "SourceSans3-SemiboldItalic",
  boldItalic: "SourceSans3-BoldItalic",
} as const;

const UI_FONT_FOR_WEIGHT = {
  "400": UI_FONT.regular,
  "500": UI_FONT.medium,
  "600": UI_FONT.semibold,
  "700": UI_FONT.bold,
} as const;

export function uiFontFamily(weight: keyof typeof UI_FONT_FOR_WEIGHT): string {
  return UI_FONT_FOR_WEIGHT[weight];
}
