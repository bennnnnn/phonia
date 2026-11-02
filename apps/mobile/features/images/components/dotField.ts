/**
 * Shared look of the image-gen waiting card's dot field: grid sizes, colors,
 * and the Skia shader that draws the moving wave.
 *
 * Nothing here imports Skia at load time. `dotWaveEffect()` asks the repo's
 * probe (`isSkiaAvailable`, false in Expo Go) first and only then requires
 * Skia and compiles the shader, once. Without it the card uses the Skia-free
 * wave (`DotCutoutWave`).
 */
import type { SkRuntimeEffect } from "@shopify/react-native-skia";

import { isSkiaAvailable } from "@/lib/skiaAvailability";
import type { Theme } from "@/lib/theme";

/** Waiting state: a fine grid. */
export const WAVE_PITCH = 13;
export const WAVE_DOT_RADIUS = 1.25;
/** Extra radius at the crest of the wave, as a share of the dot radius. */
export const WAVE_SWELL = 0.55;
/**
 * Seconds before the shader clock starts over. The band crosses twice and the
 * swell turns once in this time, so the restart is seamless.
 */
export const DOT_WAVE_LOOP_S = 10;

/** Play state: a coarser grid, sized so a small card still fits ~6 columns. */
export function playPitch(cardWidth: number): number {
  return Math.min(26, Math.max(20, Math.round(cardWidth / 6.4)));
}
export const PLAY_GRID_DOT_RADIUS = 2.5;

export type DotInk = { color: string; opacity: number };

export type DotFieldPalette = {
  /** Resting dots. Lighter ink on dark so they read on the dark surface. */
  dot: DotInk;
  /** Wave crest, snake and food. */
  accent: DotInk;
  /** The faint grid behind the dot game. */
  playGrid: DotInk;
};

export function dotFieldPalette(theme: Theme): DotFieldPalette {
  const ink = theme.isDark ? theme.textSecondary : theme.textTertiary;
  return {
    dot: { color: ink, opacity: theme.isDark ? 0.3 : 0.26 },
    accent: { color: theme.accent, opacity: theme.isDark ? 0.95 : 0.85 },
    playGrid: { color: ink, opacity: theme.isDark ? 0.22 : 0.16 },
  };
}

/**
 * One dot per grid cell. Each pixel finds its nearest dot center, then a soft
 * diagonal band (top-left to bottom-right, one crossing every 5 s) and a slow
 * cross swell decide how far that dot leans toward the accent and how much it
 * grows. Coverage is a smoothstep over about a pixel, so dots stay round and
 * crisp at any density. Output is premultiplied, as Skia expects.
 */
const DOT_WAVE_SKSL = `
uniform float2 uSize;
uniform float2 uOrigin;
uniform float2 uCount;
uniform float uPitch;
uniform float uRadius;
uniform float uSwell;
uniform float uAa;
uniform float uTime;
uniform float4 uBase;
uniform float4 uAccent;

const float TAU = 6.28318530718;

half4 main(float2 pos) {
  float2 index = floor((pos - uOrigin) / uPitch + 0.5);
  if (index.x < 0.0 || index.y < 0.0 || index.x > uCount.x - 1.0 || index.y > uCount.y - 1.0) {
    return half4(0.0);
  }
  float2 center = uOrigin + index * uPitch;
  float2 uv = center / uSize;
  float along = (uv.x * 0.75 + uv.y) / 1.75;
  float band = 0.5 + 0.5 * cos(TAU * (along - uTime * 0.2));
  band = band * band * band * band;
  float swell = 0.5 + 0.5 * cos(TAU * ((uv.x - uv.y * 0.5) * 0.9 + uTime * 0.1));
  float glow = clamp(band * (0.55 + 0.45 * swell), 0.0, 1.0);
  float radius = uRadius * (1.0 + uSwell * glow);
  float cover = 1.0 - smoothstep(radius - uAa, radius + uAa, distance(pos, center));
  float4 color = mix(uBase, uAccent, glow);
  float alpha = color.a * cover;
  return half4(half3(color.rgb * alpha), half(alpha));
}
`;

let compiled: SkRuntimeEffect | null | undefined;

/**
 * The compiled wave shader, or `null` when this build should not use Skia.
 * The repo probe decides first: a stale or mismatched native Skia can crash
 * natively, which no try/catch here would catch, so Skia is never required
 * when the probe says no.
 */
export function dotWaveEffect(): SkRuntimeEffect | null {
  if (!isSkiaAvailable()) return null;
  if (compiled !== undefined) return compiled;
  try {
    // A lazy require keeps Skia out of the chat's start-up.
    const { Skia } =
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- deliberate lazy probe
      require("@shopify/react-native-skia") as typeof import("@shopify/react-native-skia");
    compiled = Skia.RuntimeEffect.Make(DOT_WAVE_SKSL) ?? null;
  } catch {
    compiled = null;
  }
  return compiled;
}
