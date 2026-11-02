import { triangleSidesVertices } from "@/lib/math/geometryBlock";

describe("triangle side placement", () => {
  it.each([[3, 4, 5], [5, 4, 3], [6, 5, 5], [5, 5, 6]])(
    "matches the renderer's labels and congruence ticks for a=%s, b=%s, c=%s",
    (a, b, c) => {
      const v = triangleSidesVertices(a, b, c);
      expect(Math.hypot(v.x1 - v.x0, v.y1 - v.y0)).toBeCloseTo(a, 10);
      expect(Math.hypot(v.x2 - v.x1, v.y2 - v.y1)).toBeCloseTo(b, 10);
      expect(Math.hypot(v.x0 - v.x2, v.y0 - v.y2)).toBeCloseTo(c, 10);
    },
  );
});
