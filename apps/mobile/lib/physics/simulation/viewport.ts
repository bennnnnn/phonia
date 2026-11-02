/** The scene's canvas: its size, and world units to screen pixels. */
import { type SimulationSpec } from "@/lib/physics/simulation/spec";

/**
 * Water in a tank: a domain colour, like an element's in a molecule, picked
 * per scheme. The fill is a translucent wash of it and the surface line is it
 * at full strength.
 */
export const FLUID_TINT = { light: "#2F7ED8", dark: "#64AEF5" } as const;

/** Padding inside the scene canvas, around the scene box. */
export const SIMULATION_PAD = 24;
/** Tallest a scene canvas grows (square and tall scenes). */
export const SIMULATION_HEIGHT = 240;
/** Shortest a scene canvas shrinks (wide scenes). */
export const SIMULATION_MIN_HEIGHT = 136;

export type SimulationTransform = {
  scale: number;
  offsetX: number;
  offsetY: number;
  height: number;
};

/**
 * Size the viewport to the scene instead of vertically centring every scene
 * in a fixed tall box. Wide scenes (projectiles and collisions) therefore sit
 * directly below their title, while square/tall scenes retain the full canvas.
 */
export function simulationViewportHeight(
  spec: SimulationSpec,
  width: number,
  pad: number,
  minHeight: number,
  maxHeight: number,
): number {
  const innerW = Math.max(width - pad * 2, 1);
  const worldW = spec.xMax - spec.xMin;
  const worldH = spec.yMax - spec.yMin;
  const heightAtFullWidth = (worldH / worldW) * innerW + pad * 2;
  return Math.max(minHeight, Math.min(maxHeight, heightAtFullWidth));
}

/** Keep measured canvas text fully inside the drawable viewport. */
export function clampCanvasLabelX(
  desiredX: number,
  labelWidth: number,
  canvasWidth: number,
  inset = 4,
): number {
  "worklet";
  const maxX = Math.max(inset, canvasWidth - inset - Math.max(0, labelWidth));
  return Math.max(inset, Math.min(maxX, desiredX));
}

/** Skia text uses a baseline, so the top also needs one font-height of room. */
export function clampCanvasLabelBaseline(
  desiredY: number,
  fontSize: number,
  canvasHeight: number,
  inset = 4,
): number {
  "worklet";
  const minY = inset + Math.max(0, fontSize);
  const maxY = Math.max(minY, canvasHeight - inset);
  return Math.max(minY, Math.min(maxY, desiredY));
}

/**
 * World units to screen pixels, with **one** scale for both axes.
 *
 * Stretching each axis to fill the box is what a graph does, and it would be
 * wrong here: an orbit would come out an ellipse, and a projectile's launch
 * angle would not be the angle it was launched at. The scene is letterboxed
 * into the box instead, and centred in whichever direction has slack.
 */
export function simulationTransform(
  spec: SimulationSpec,
  width: number,
  height: number,
  pad: number,
): SimulationTransform {
  const innerW = Math.max(width - pad * 2, 1);
  const innerH = Math.max(height - pad * 2, 1);
  const worldW = spec.xMax - spec.xMin;
  const worldH = spec.yMax - spec.yMin;
  const scale = Math.min(innerW / worldW, innerH / worldH);
  return {
    scale,
    offsetX: pad + (innerW - worldW * scale) / 2 - spec.xMin * scale,
    // y grows upward in the world and downward on screen, so the offset is
    // measured from the bottom of the letterboxed area.
    offsetY: pad + innerH - (innerH - worldH * scale) / 2 + spec.yMin * scale,
    height,
  };
}

export type ScreenPoint = { px: number; py: number };

export function worldToScreen(x: number, y: number, t: SimulationTransform): ScreenPoint {
  "worklet";
  return { px: x * t.scale + t.offsetX, py: t.offsetY - y * t.scale };
}

/** Screen-space samples, mapped once so the worklet only ever indexes. */
export function projectPath(path: number[][], t: SimulationTransform): ScreenPoint[] {
  return path.map(([x, y]) => worldToScreen(x, y, t));
}
