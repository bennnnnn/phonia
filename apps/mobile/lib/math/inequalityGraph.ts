import type { InequalityGraphSpec } from "@/lib/math/graphSpec";

type Point = [number, number];

/** Clip the viewport rectangle against a verified affine half-plane. This is
 * drawing geometry only: the client never parses or solves the expression. */
export function clipInequalityRegion(spec: InequalityGraphSpec): {
  region: Point[];
  boundary: Point[];
} | null {
  const corners: Point[] = [
    [spec.x_min, spec.y_min], [spec.x_max, spec.y_min],
    [spec.x_max, spec.y_max], [spec.x_min, spec.y_max],
  ];
  // Two positive scale factors preserve the relation while preventing
  // coefficient*coordinate overflow on otherwise finite JSON numbers.
  const coefficientScale = Math.max(Math.abs(spec.a), Math.abs(spec.b), Math.abs(spec.c));
  const coordinateScale = Math.max(
    1,
    ...(spec.a !== 0 ? [Math.abs(spec.x_min), Math.abs(spec.x_max)] : []),
    ...(spec.b !== 0 ? [Math.abs(spec.y_min), Math.abs(spec.y_max)] : []),
  );
  const a = spec.a / coefficientScale;
  const b = spec.b / coefficientScale;
  const c = spec.c / coefficientScale / coordinateScale;
  const direction = spec.comparator.startsWith("<") ? 1 : -1;
  const side = ([x, y]: Point) => direction * (a * (x / coordinateScale) + b * (y / coordinateScale) - c);
  const sides = corners.map(side);
  // A nonzero affine relation cannot contain a whole rectangle in its
  // boundary. If float precision erased every term, do not shade falsely.
  if (sides.some((value) => !Number.isFinite(value)) || sides.every((value) => value === 0)) return null;
  const region: Point[] = [];
  const boundary: Point[] = [];
  const addBoundary = (point: Point) => {
    if (!boundary.some(([x, y]) => x === point[0] && y === point[1])) boundary.push(point);
  };
  for (let i = 0; i < corners.length; i += 1) {
    const from = corners[i];
    const to = corners[(i + 1) % corners.length];
    const fromSide = sides[i];
    const toSide = sides[(i + 1) % corners.length];
    // Fill the closure in both cases. The boundary's dashed/solid stroke
    // communicates whether points on the line belong to the solution set.
    if (fromSide <= 0) region.push(from);
    if (fromSide === 0) addBoundary(from);
    if ((fromSide < 0 && toSide > 0) || (fromSide > 0 && toSide < 0)) {
      const amount = fromSide / (fromSide - toSide);
      const intersection: Point = [
        from[0] + (to[0] - from[0]) * amount,
        from[1] + (to[1] - from[1]) * amount,
      ];
      region.push(intersection);
      addBoundary(intersection);
    }
  }
  return { region: region.length >= 3 ? region : [], boundary };
}
