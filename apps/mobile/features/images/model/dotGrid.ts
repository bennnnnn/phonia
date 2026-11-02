/**
 * Geometry for the dot grid on the image-gen waiting card. The grid is
 * centered in the card so the margins match on every side; both the wave
 * shader and the dot game place dots with this one layout.
 */

/** One grid position: column `x`, row `y`. */
export type Cell = { readonly x: number; readonly y: number };

export type DotGrid = {
  readonly cols: number;
  readonly rows: number;
  /** Distance between neighboring dot centers. */
  readonly pitch: number;
  /** Center of the dot at column 0, row 0. */
  readonly originX: number;
  readonly originY: number;
};

/** As many dots as fit at `pitch`, centered in a `width` × `height` card. */
export function dotGridLayout(width: number, height: number, pitch: number): DotGrid {
  const step = pitch > 0 ? pitch : 1;
  const cols = Math.max(1, Math.floor(Math.max(0, width) / step));
  const rows = Math.max(1, Math.floor(Math.max(0, height) / step));
  return {
    cols,
    rows,
    pitch: step,
    originX: (width - (cols - 1) * step) / 2,
    originY: (height - (rows - 1) * step) / 2,
  };
}

/** Center point of a cell, in card coordinates. */
export function cellCenter(grid: DotGrid, cell: Cell): { x: number; y: number } {
  return {
    x: grid.originX + cell.x * grid.pitch,
    y: grid.originY + cell.y * grid.pitch,
  };
}

/** The cell nearest a point in the card (a tap), clamped to the grid. */
export function cellAtPoint(grid: DotGrid, x: number, y: number): Cell {
  const col = Math.round((x - grid.originX) / grid.pitch);
  const row = Math.round((y - grid.originY) / grid.pitch);
  return {
    x: clamp(Number.isFinite(col) ? col : 0, 0, grid.cols - 1),
    y: clamp(Number.isFinite(row) ? row : 0, 0, grid.rows - 1),
  };
}

/**
 * SVG path data for a `width` × `height` cover with a round hole of `radius`
 * at every dot of `grid`. Fill it with `fill-rule="evenodd"` in the card's
 * color: whatever is drawn beneath shows only through the dots. The cover
 * overhangs the card by one point so no edge of the layers below peeks out.
 */
export function dotHolesPath(grid: DotGrid, width: number, height: number, radius: number): string {
  const r = num(radius);
  const across = num(radius * 2);
  const parts = [`M-1 -1H${num(width + 1)}V${num(height + 1)}H-1Z`];
  for (let y = 0; y < grid.rows; y += 1) {
    for (let x = 0; x < grid.cols; x += 1) {
      const center = cellCenter(grid, { x, y });
      // Two half-circle arcs from the left edge of the hole and back.
      parts.push(
        `M${num(center.x - radius)} ${num(center.y)}a${r} ${r} 0 1 0 ${across} 0a${r} ${r} 0 1 0 -${across} 0Z`,
      );
    }
  }
  return parts.join("");
}

/** Compact path number: at most two decimals, no trailing zeros. */
function num(value: number): string {
  return String(Math.round(value * 100) / 100);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
