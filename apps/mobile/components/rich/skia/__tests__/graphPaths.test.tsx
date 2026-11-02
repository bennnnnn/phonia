/**
 * Pins the explorer's path builders: every segment, fill, marker and grid line
 * as the ops it records, and the tick labels with where they sit.
 */
import type { DrawnSeries } from "@/hooks/useInteractiveGraph";
import {
  buildFillPath,
  buildMarkerPath,
  buildSeriesPath,
  computeChrome,
} from "@/components/rich/skia/graphPaths";

jest.mock("@shopify/react-native-skia", () => {
  const actual = jest.requireActual("@shopify/react-native-skia");
  const round = (value: number) => Math.round(value * 100) / 100;
  const makePath = () => {
    const ops: string[] = [];
    const path = {
      ops,
      moveTo: (x: number, y: number) => ops.push(`M${round(x)},${round(y)}`) && path,
      lineTo: (x: number, y: number) => ops.push(`L${round(x)},${round(y)}`) && path,
      addCircle: (x: number, y: number, r: number) =>
        ops.push(`C${round(x)},${round(y)},${round(r)}`) && path,
      close: () => ops.push("Z") && path,
    };
    return path;
  };
  return { ...actual, Skia: { ...actual.Skia, Path: { Make: makePath } } };
});

type Recorded = { ops: string[] };
const ops = (path: unknown) => (path as Recorded).ops.join(" ");

const VIEWS = [
  { xMin: -6, xMax: 6, yMin: -4, yMax: 4 },
  { xMin: 2, xMax: 9, yMin: 1, yMax: 30 },
  { xMin: -0.01, xMax: 0.02, yMin: -1e-3, yMax: 5e-3 },
];

function series(partial: Partial<DrawnSeries>): DrawnSeries {
  return {
    id: "0",
    expr: "y = x^2",
    visible: true,
    locked: true,
    color: "#2563eb",
    points: [
      [-2, 4],
      [-1, 1],
      [0, 0],
      [1, 1],
      [2, 4],
    ],
    invalid: false,
    cmp: "=",
    ...partial,
  };
}

const SERIES: DrawnSeries[] = [
  series({}),
  series({ cmp: "<=" }),
  series({ cmp: ">" }),
  series({ visible: false }),
  series({ points: [[0, 1], [Number.NaN, 2], [1, 3], [2, Number.POSITIVE_INFINITY], [3, 4]] }),
  series({
    segments: [
      [
        [-3, -1],
        [-1, -3],
      ],
      [
        [1, 3],
        [3, 1],
      ],
      [[5, 5]],
    ],
  }),
];

describe("graph explorer path builders", () => {
  it.each(VIEWS.map((view, index) => [index, view]))("draws every series in view %i", (_, view) => {
    const lines = SERIES.map((row, index) =>
      [
        `${index} series ${ops(buildSeriesPath(row, view, 320, 240, 28))}`,
        `${index} fill ${ops(buildFillPath(row, view, 320, 240, 28))}`,
      ].join("\n"),
    );
    lines.push(`missing ${ops(buildSeriesPath(undefined, view, 320, 240, 28))}`);
    lines.push(`markers ${ops(buildMarkerPath([SERIES[0]!], view, 320, 240, 28))}`);
    lines.push(`markers-two ${ops(buildMarkerPath(SERIES.slice(0, 2), view, 320, 240, 28))}`);
    expect(lines.join("\n")).toMatchSnapshot();
  });

  it.each(VIEWS.map((view, index) => [index, view]))("lays out the grid and ticks in view %i", (_, view) => {
    const font = { measureText: (text: string) => ({ x: 0, y: 0, width: text.length * 6, height: 10 }) };
    for (const withFont of [null, font]) {
      const chrome = computeChrome(view, 320, 240, 28, withFont);
      expect({
        grid: ops(chrome.grid),
        axes: ops(chrome.axes),
        xLabels: chrome.xLabels,
        yLabels: chrome.yLabels,
        origin: chrome.origin,
        originInView: chrome.originInView,
        xNamePos: chrome.xNamePos,
        yNamePos: chrome.yNamePos,
      }).toMatchSnapshot();
    }
  });
});

describe("an x-range given in π", () => {
  it("labels the Skia x axis in π", () => {
    const view = { xMin: 0, xMax: 2 * Math.PI, yMin: -2, yMax: 2 };
    const chrome = computeChrome(view, 320, 240, 28, null, true);
    expect(chrome.xLabels.map((label) => label.text)).toEqual(["π/2", "π", "3π/2", "2π"]);
  });
});
