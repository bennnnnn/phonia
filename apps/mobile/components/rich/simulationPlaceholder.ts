/**
 * How tall a `simulation` fence's card will be, so its list cell does not jump
 * when the renderer arrives. It reads the fence with the physics parsers and
 * lays it out with the renderers' own pure layout, well over 100 KB of source,
 * so `LazyHeavyRich` loads this on demand too rather than with the chat screen.
 */
import { physicsDiagramPlaceholderHeight } from "@/components/rich/diagrams/placeholder";
import { FIGURE_TITLE_HEIGHT, figureWidth } from "@/components/rich/figure";
import type { DiagramKind } from "@/lib/physics/diagramKind";
import {
  parseSimulationSpec,
  SIMULATION_HEIGHT,
  SIMULATION_MIN_HEIGHT,
  SIMULATION_PAD,
  simulationIsAnimated,
  simulationViewportHeight,
} from "@/lib/physics/simulation";
import { Space } from "@/lib/space";

/**
 * The height the scene will take once loaded — title, canvas sized to the
 * scene's aspect, and the play button when something moves. Unreadable
 * content keeps the old fixed guess; the block shows a one-line fallback for
 * it anyway.
 */
export function simulationPlaceholderHeight(
  content: string,
  screenWidth: number,
): number {
  const spec = parseSimulationSpec(content);
  if (!spec) return SIMULATION_HEIGHT;
  const canvas = simulationViewportHeight(
    spec,
    figureWidth(screenWidth),
    SIMULATION_PAD,
    SIMULATION_MIN_HEIGHT,
    SIMULATION_HEIGHT,
  );
  const control = simulationIsAnimated(spec) ? Space.xxs + Space.minTouch : 0;
  return Space.xs * 2 + FIGURE_TITLE_HEIGHT + canvas + control;
}

/** A circuit, a ray diagram or a wave (`kind`) has its own layout; a body scene the one above. */
export function simulationFencePlaceholderHeight(
  content: string,
  kind: DiagramKind | null,
  screenWidth: number,
): number {
  return kind
    ? physicsDiagramPlaceholderHeight(content, screenWidth)
    : simulationPlaceholderHeight(content, screenWidth);
}
