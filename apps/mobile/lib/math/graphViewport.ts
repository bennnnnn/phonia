export type GraphView = {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
};

/** Default school window: x ≈ −6…6 so labels include −3…3 at unit steps. */
const DEFAULT_GRAPH_X_HALF = 6;

export function defaultInteractiveBounds(plotAspect: number): GraphView {
  const aspect = Number.isFinite(plotAspect) && plotAspect > 0.3 ? plotAspect : 1.7;
  const xHalf = DEFAULT_GRAPH_X_HALF;
  const yHalf = xHalf / aspect;
  return { xMin: -xHalf, xMax: xHalf, yMin: -yHalf, yMax: yHalf };
}

/**
 * Widen a window around its center. The Skia explorer samples curves over an
 * expanded window so mid-gesture pan/zoom has runway before the JS resample
 * lands on gesture end.
 */
export function expandGraphView(view: GraphView, factor: number): GraphView {
  const f = Number.isFinite(factor) && factor > 0 ? factor : 1;
  const cx = (view.xMin + view.xMax) / 2;
  const cy = (view.yMin + view.yMax) / 2;
  const xHalf = ((view.xMax - view.xMin) / 2) * f;
  const yHalf = ((view.yMax - view.yMin) / 2) * f;
  return { xMin: cx - xHalf, xMax: cx + xHalf, yMin: cy - yHalf, yMax: cy + yHalf };
}
