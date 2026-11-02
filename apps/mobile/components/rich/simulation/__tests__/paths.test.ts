/**
 * The Skia paths a simulation scene draws its fixed parts, box bodies and
 * springs with, read back as the commands they record.
 */
import {
  boxPath,
  pivotPath,
  polygonPath,
  rectPath,
  springPath,
  wallPath,
} from "@/components/rich/simulation/paths";
import { segmentsPath } from "@/components/rich/skia/paths";
import { PIVOT_SIZE } from "@/lib/physics/simulation";

jest.mock("@shopify/react-native-skia", () => ({
  Skia: {
    Path: {
      Make: () => {
        const ops: (string | number)[][] = [];
        const path = {
          ops,
          moveTo: (x: number, y: number) => ops.push(["M", x, y]) && path,
          lineTo: (x: number, y: number) => ops.push(["L", x, y]) && path,
          close: () => ops.push(["Z"]) && path,
        };
        return path;
      },
    },
  },
}));

/** The commands a path recorded, to the thousandth of a pixel. */
function commands(path: unknown): (string | number)[][] {
  return (path as { ops: (string | number)[][] }).ops.map((op) =>
    op.map((part) => (typeof part === "number" ? Math.round(part * 1000) / 1000 || 0 : part)),
  );
}

describe("simulation paths", () => {
  it("stands a wall 32 px tall on its anchor, stopping at the ground", () => {
    expect(commands(wallPath({ px: 10, py: 50 }, null))).toEqual([
      ["M", 10, 34],
      ["L", 10, 66],
    ]);
    expect(commands(wallPath({ px: 10, py: 50 }, 60))).toEqual([
      ["M", 10, 34],
      ["L", 10, 60],
    ]);
    // A floor below the wall's foot leaves the wall whole.
    expect(commands(wallPath({ px: 10, py: 50 }, 80))[1]).toEqual(["L", 10, 66]);
  });

  it("hangs a pivot's triangle below its point", () => {
    const drop = PIVOT_SIZE * 1.4;
    expect(commands(pivotPath({ px: 100, py: 40 }))).toEqual([
      ["M", 100, 40],
      ["L", 100 - PIVOT_SIZE, 40 + drop],
      ["L", 100 + PIVOT_SIZE, 40 + drop],
      ["Z"],
    ]);
  });

  it("closes a polygon through its points, and a rectangle through its corners", () => {
    const triangle = [
      { px: 0, py: 0 },
      { px: 4, py: 0 },
      { px: 0, py: 3 },
    ];
    expect(commands(polygonPath(triangle))).toEqual([
      ["M", 0, 0],
      ["L", 4, 0],
      ["L", 0, 3],
      ["Z"],
    ]);
    expect(commands(rectPath({ x: 1, y: 2, width: 10, height: 5 }))).toEqual([
      ["M", 1, 2],
      ["L", 11, 2],
      ["L", 11, 7],
      ["L", 1, 7],
      ["Z"],
    ]);
  });

  it("draws each hatch of a support as its own stroke", () => {
    const hatches = [
      { x1: 0, y1: 0, x2: 5, y2: 5 },
      { x1: 8, y1: 0, x2: 13, y2: 5 },
    ];
    expect(commands(segmentsPath(hatches))).toEqual([
      ["M", 0, 0],
      ["L", 5, 5],
      ["M", 8, 0],
      ["L", 13, 5],
    ]);
  });

  it("turns a box body by its angle about its centre", () => {
    expect(commands(boxPath(50, 50, 10, 0))).toEqual([
      ["M", 60, 60],
      ["L", 40, 60],
      ["L", 40, 40],
      ["L", 60, 40],
      ["Z"],
    ]);
    // Turned an eighth of a circle, the square stands on a corner, 10√2 from its centre.
    expect(commands(boxPath(50, 50, 10, Math.PI / 4))).toEqual([
      ["M", 50, 64.142],
      ["L", 35.858, 50],
      ["L", 50, 35.858],
      ["L", 64.142, 50],
      ["Z"],
    ]);
  });

  it("zigzags a spring eight coils from its anchor to the body", () => {
    const ops = commands(springPath({ px: 0, py: 0 }, { px: 160, py: 0 }));
    expect(ops[0]).toEqual(["M", 0, 0]);
    expect(ops[ops.length - 1]).toEqual(["L", 160, 0]);
    // Fifteen turning points, 10 px apart, alternating 8 px either side.
    const turns = ops.slice(1, -1);
    expect(turns).toHaveLength(15);
    turns.forEach((op, i) => expect(op).toEqual(["L", 10 * (i + 1), i % 2 === 0 ? -8 : 8]));
  });

  it("draws a spring shorter than a pixel as a straight line", () => {
    expect(commands(springPath({ px: 5, py: 5 }, { px: 5.5, py: 5.5 }))).toEqual([
      ["M", 5, 5],
      ["L", 5.5, 5.5],
    ]);
  });
});
