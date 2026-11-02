/**
 * WCAG 2.x contrast for the theme's colors, shared by the token tests and the
 * component tests that check a pair as it is drawn.
 */

/** Normal-size text (WCAG AA). */
export const AA = 4.5;

/** WCAG 2.x relative luminance of a #RRGGBB color (sRGB). */
function relativeLuminance(hex: string): number {
  const n = parseInt(hex.replace("#", ""), 16);
  const channels = [n >> 16, (n >> 8) & 0xff, n & 0xff].map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** An `rgba(...)` laid over an opaque #RRGGBB plane, as #rrggbb. Other colors come back as they are. */
export function compositeOver(color: string, underlay: string): string {
  const match = color.match(/^rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)$/);
  if (!match) return color;
  const base = underlay.replace("#", "");
  const alpha = Number(match[4]);
  const channels = [0, 1, 2].map((index) =>
    Math.round(
      Number(match[index + 1]) * alpha + parseInt(base.slice(index * 2, index * 2 + 2), 16) * (1 - alpha),
    ),
  );
  return `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}
