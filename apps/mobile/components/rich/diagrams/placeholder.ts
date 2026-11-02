/**
 * The height a circuit, ray or wave diagram takes before its chunk loads, so a
 * list cell does not jump. Kept apart from the renderers so the chat bundle
 * does not import them: this reads the fence with the same parser and lays it
 * out with the same pure layout, and imports no Skia.
 */
import { FIGURE_TITLE_HEIGHT, figureWidth } from "@/components/rich/figure";
import { diagramKind } from "@/lib/physics/diagramKind";
import { Space } from "@/lib/space";
import {
  parsePhysicsDiagram,
  physicsDiagramCanvasHeight,
  physicsDiagramIsAnimated,
} from "@/components/rich/diagrams/spec";

/** The fallback line a malformed fence shows: its margins, padding and one line of text. */
export const PHYSICS_DIAGRAM_FALLBACK_HEIGHT = Space.xs * 2 + Space.sm * 2 + 18;

export function physicsDiagramPlaceholderHeight(content: string, screenWidth: number): number {
  const kind = diagramKind(content);
  const spec = kind ? parsePhysicsDiagram(content, kind) : null;
  if (!spec) return PHYSICS_DIAGRAM_FALLBACK_HEIGHT;
  const canvas = physicsDiagramCanvasHeight(spec, figureWidth(screenWidth));
  const control = physicsDiagramIsAnimated(spec) ? Space.xxs + Space.minTouch : 0;
  return Space.xs * 2 + FIGURE_TITLE_HEIGHT + canvas + control;
}
