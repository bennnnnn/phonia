/**
 * Which angle-related elements a rectangle diagram should render. A
 * rectangle's own corners are always 90° — the right-angle bracket glyph is
 * the conventional way to say that. The diagonal-vs-base angle (`angle_deg`
 * in the spec) is a *different*, generally non-90° quantity, so it must
 * never be drawn at the same spot as that bracket — labeling it right next
 * to a glyph that means "90°" reads as a contradiction (e.g. a bracket next
 * to "51.3°"). Only show the diagonal's angle when a diagonal is actually
 * being drawn; suppress the bracket in that case since the angle of
 * interest there isn't the corner's.
 */
export function rectangleAngleDisplay(spec: {
  type: "rectangle" | "square";
  show_angle?: boolean;
  show_diagonal?: boolean;
}): { showCornerBracket: boolean; showDiagonalAngleLabel: boolean } {
  const isSquare = spec.type === "square";
  const showAngle = !!spec.show_angle;
  const showDiagonal = !!spec.show_diagonal;
  return {
    showCornerBracket: isSquare || (showAngle && !showDiagonal),
    showDiagonalAngleLabel: !isSquare && showAngle && showDiagonal,
  };
}

/**
 * SVG path for a small arc at the top-left corner of a rectangle, from the
 * top edge toward the TL→BR diagonal. Encodes the same diagonal-vs-base
 * angle shown as `∠ N°` text — a curved mark so the angle reads as a
 * school-diagram cue, not a bare floating number.
 *
 * Coordinates use SVG's y-down convention (`atan2(height, width)`).
 */
export function diagonalAngleArcPath(
  originX: number,
  originY: number,
  width: number,
  height: number,
  radius = 18,
): string {
  const w = Math.max(width, 1e-6);
  const h = Math.max(height, 1e-6);
  const theta = Math.atan2(h, w);
  const r = Math.min(radius, w * 0.28, h * 0.28);
  const x1 = originX + r;
  const y1 = originY;
  const x2 = originX + r * Math.cos(theta);
  const y2 = originY + r * Math.sin(theta);
  // sweep-flag 1 = clockwise in SVG → from +x down into the diagonal.
  return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
}

type AngleLeader = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type VertexAngleMark = {
  path: string;
  labelX: number;
  labelY: number;
  text: string;
  deg: number;
  labelWidth: number;
  labelHeight: number;
  leader: AngleLeader | null;
};

const ANGLE_LABEL_FONT = 11;
const RIGHT_ANGLE_SQUARE = 14;

/** Backdrop size so `.5°` is not sitting on a stroke. */
export function estimateAngleLabelSize(text: string): { width: number; height: number } {
  return { width: Math.max(24, text.length * 6.6 + 10), height: ANGLE_LABEL_FONT + 7 };
}

function closestPointOnRect(
  px: number,
  py: number,
  cx: number,
  cy: number,
  w: number,
  h: number,
): { x: number; y: number } {
  return {
    x: Math.max(cx - w / 2, Math.min(cx + w / 2, px)),
    y: Math.max(cy - h / 2, Math.min(cy + h / 2, py)),
  };
}

/** School-diagram degree label: `90°` / `36.9°`. */
export function formatAngleDeg(deg: number): string {
  const rounded = Math.round(deg * 10) / 10;
  if (Math.abs(rounded - Math.round(rounded)) < 0.05) {
    return `${Math.round(rounded)}°`;
  }
  return `${rounded.toFixed(1)}°`;
}

export function isRightAngleDeg(deg: number, tolerance = 0.6): boolean {
  return Math.abs(deg - 90) < tolerance;
}

/**
 * Interior angle at vertex B of triangle ABC (SVG y-down). The shorter arc
 * is the interior for convex polygons.
 */
function vertexAngleMark(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
  radius = 16,
): VertexAngleMark {
  const a1 = Math.atan2(ay - by, ax - bx);
  const a2 = Math.atan2(cy - by, cx - bx);
  let delta = a2 - a1;
  while (delta > Math.PI) delta -= 2 * Math.PI;
  while (delta < -Math.PI) delta += 2 * Math.PI;
  const deg = (Math.abs(delta) * 180) / Math.PI;
  const r = Math.max(radius, 8);
  const x1 = bx + r * Math.cos(a1);
  const y1 = by + r * Math.sin(a1);
  const x2 = bx + r * Math.cos(a1 + delta);
  const y2 = by + r * Math.sin(a1 + delta);
  const sweep = delta > 0 ? 1 : 0;
  const mid = a1 + delta / 2;
  const text = formatAngleDeg(deg);
  const { width: labelWidth, height: labelHeight } = estimateAngleLabelSize(text);
  const half = Math.abs(delta) / 2;
  const fromWedge = (labelWidth / 2 + 5) / Math.sin(Math.max(half, 1e-3));
  const minSide = Math.min(Math.hypot(ax - bx, ay - by), Math.hypot(cx - bx, cy - by));
  const interiorR = Math.min(Math.max(r + 18, fromWedge), Math.max(minSide * 0.42, r + 18));
  const inX = bx + interiorR * Math.cos(mid);
  const inY = by + interiorR * Math.sin(mid);
  const right = isRightAngleDeg(deg);
  const wedgeW = 2 * interiorR * Math.sin(half);
  const overlapsSquare = right && interiorR < RIGHT_ANGLE_SQUARE + labelHeight / 2 + 8;
  const fitsInside =
    !overlapsSquare &&
    wedgeW >= labelWidth * 0.75 &&
    interiorR + labelHeight / 2 < minSide * 0.55;
  if (fitsInside) {
    return {
      path: `M ${x1} ${y1} A ${r} ${r} 0 0 ${sweep} ${x2} ${y2}`,
      labelX: inX,
      labelY: inY,
      text,
      deg,
      labelWidth,
      labelHeight,
      leader: null,
    };
  }
  const outR = Math.max(r + 22, 32 + Math.max(labelWidth, labelHeight) * 0.4);
  const labelX = bx + outR * Math.cos(mid + Math.PI);
  const labelY = by + outR * Math.sin(mid + Math.PI);
  const startX = bx + Math.min(r, 12) * Math.cos(mid);
  const startY = by + Math.min(r, 12) * Math.sin(mid);
  const end = closestPointOnRect(startX, startY, labelX, labelY, labelWidth, labelHeight);
  return {
    path: `M ${x1} ${y1} A ${r} ${r} 0 0 ${sweep} ${x2} ${y2}`,
    labelX,
    labelY,
    text,
    deg,
    labelWidth,
    labelHeight,
    leader: { x1: startX, y1: startY, x2: end.x, y2: end.y },
  };
}

/** Grow the SVG so exterior degree labels are not clipped. */
export function padDiagramForAngleLabels(
  vertices: { x: number; y: number }[],
  svgW: number,
  svgH: number,
  margin = 10,
): { vertices: { x: number; y: number }[]; svgW: number; svgH: number } {
  const marks = polygonInteriorAngleMarks(vertices);
  let minX = 0;
  let minY = 0;
  let maxX = svgW;
  let maxY = svgH;
  for (const m of marks) {
    minX = Math.min(minX, m.labelX - m.labelWidth / 2);
    minY = Math.min(minY, m.labelY - m.labelHeight / 2);
    maxX = Math.max(maxX, m.labelX + m.labelWidth / 2);
    maxY = Math.max(maxY, m.labelY + m.labelHeight / 2);
  }
  const dx = minX < margin ? margin - minX : 0;
  const dy = minY < margin ? margin - minY : 0;
  return {
    vertices: dx || dy ? vertices.map((v) => ({ x: v.x + dx, y: v.y + dy })) : vertices,
    svgW: maxX + dx + margin,
    svgH: maxY + dy + margin,
  };
}

export function polygonInteriorAngleMarks(
  vertices: { x: number; y: number }[],
  radius = 16,
): VertexAngleMark[] {
  const n = vertices.length;
  if (n < 3) return [];
  return vertices.map((b, i) => {
    const a = vertices[(i + n - 1) % n];
    const c = vertices[(i + 1) % n];
    return vertexAngleMark(a.x, a.y, b.x, b.y, c.x, c.y, radius);
  });
}
