/**
 * The ray diagram's layout, read off what it draws: where the element, the
 * rays, their heads, the focal marks and every label land on the canvas.
 *
 * Skia is replaced by a recorder, so each path arrives as its move and line
 * commands and each label as its text and baseline. The expected positions
 * come from the pure helpers in `lib/physics/optics.ts`.
 */
import { type Box } from "@/lib/physics/boxes";
import { render } from "@testing-library/react-native";

import { RayDiagram } from "@/components/rich/diagrams/RayDiagram";
import { parsePhysicsDiagram, type RayDiagramSpec } from "@/components/rich/diagrams/spec";
import { measureDiagramText } from "@/components/rich/diagrams/textWidth";
import {
  elementExtent,
  labelBox,
  labelHits,
  layoutMeasure,
  polylineSegments,
  rayMarks,
  toScreen,
  worldTransform,
  worldViewportHeight,
  type LabelPlacement,
  type ScreenPoint,
} from "@/lib/physics/optics";
import { lightTheme } from "@/lib/theme";

/** The focal mark reads "F", as in every locale, so it is placed as narrow as it ships. */
const mockT = (key: string) => (key === "rich.diagram_mark_focus" ? "F" : key);
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: mockT }) }));

jest.mock("@shopify/react-native-skia", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const React = require("react");
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const { View } = require("react-native");
  const makePath = () => {
    const cmds: (string | number)[][] = [];
    return {
      cmds,
      moveTo: (x: number, y: number) => cmds.push(["M", x, y]),
      lineTo: (x: number, y: number) => cmds.push(["L", x, y]),
      close: () => cmds.push(["Z"]),
      addCircle: (x: number, y: number, r: number) => cmds.push(["C", x, y, r]),
    };
  };
  type MockProps = Record<string, unknown>;
  return {
    __esModule: true,
    Canvas: ({ children, ...rest }: MockProps) => React.createElement(View, rest, children),
    Group: ({ children, clip }: MockProps) => React.createElement("SkGroup", { clip }, children),
    Path: ({ path, children, ...rest }: MockProps) =>
      React.createElement("SkPath", { ...rest, d: (path as { cmds: unknown }).cmds }, children),
    DashPathEffect: (props: MockProps) => React.createElement("SkDash", props),
    Text: ({ font: _font, ...rest }: MockProps) => React.createElement("SkText", rest),
    Skia: {
      Path: { Make: makePath },
      XYWHRect: (x: number, y: number, width: number, height: number) => ({ x, y, width, height }),
    },
    useFont: () => ({ size: 12 }),
  };
});

type Cmd = [string, ...number[]];
type JsonNode = { type: string; props: Record<string, unknown>; children: (JsonNode | string)[] | null };
type DrawnPath = { d: Cmd[]; color: string; style?: string; strokeWidth?: number; dash?: number[] };

const WIDTH = 360;
const RAY = lightTheme.graphSeries[2];
const FOCUS = "F";

function nodes(tree: JsonNode | JsonNode[] | null): JsonNode[] {
  if (!tree) return [];
  const out: JsonNode[] = [];
  const walk = (node: JsonNode | string) => {
    if (typeof node === "string") return;
    out.push(node);
    for (const child of node.children ?? []) walk(child);
  };
  for (const node of Array.isArray(tree) ? tree : [tree]) walk(node);
  return out;
}

async function draw(fence: Record<string, unknown>) {
  const spec = parsePhysicsDiagram(JSON.stringify(fence), "rays") as RayDiagramSpec;
  if (!spec) throw new Error("expected the fence to parse");
  const { toJSON } = await render(<RayDiagram spec={spec} />);
  const all = nodes(toJSON() as JsonNode | JsonNode[] | null);
  const paths: DrawnPath[] = all
    .filter((node) => node.type === "SkPath")
    .map((node) => {
      const dash = (node.children ?? []).find((child) => typeof child !== "string" && child.type === "SkDash");
      return {
        d: node.props.d as Cmd[],
        color: node.props.color as string,
        style: node.props.style as string | undefined,
        strokeWidth: node.props.strokeWidth as number | undefined,
        dash: dash && typeof dash !== "string" ? (dash.props.intervals as number[]) : undefined,
      };
    });
  // Each label is drawn twice: its halo (stroked), then its fill.
  const labels: LabelPlacement[] = all
    .filter((node) => node.type === "SkText" && node.props.style !== "stroke")
    .map((node) => {
      const text = node.props.text as string;
      return { text, x: node.props.x as number, y: node.props.y as number, width: measureDiagramText(text) };
    });
  const height = worldViewportHeight(spec.bounds, WIDTH);
  const t = worldTransform(spec.bounds, WIDTH, height);
  return { spec, paths, labels, height, t, axis: t.offsetY };
}

const asPoints = (d: Cmd[]): ScreenPoint[] =>
  d.filter((cmd) => cmd[0] !== "Z").map((cmd) => ({ px: cmd[1], py: cmd[2] }));

function label(labels: LabelPlacement[], text: string): LabelPlacement {
  const found = labels.find((item) => item.text === text);
  if (!found) throw new Error(`no label ${text}`);
  return found;
}

function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** The server's lens example: an object 30 cm from a 10 cm converging lens. */
const LENS = {
  type: "rays",
  x_min: -34,
  x_max: 24,
  y_min: -6,
  y_max: 6,
  optics: {
    element: "converging_lens",
    focal: 10,
    object: { x: -30, height: 4, label: "object" },
    image: { x: 15, height: -2, label: "image" },
    rays: [
      { points: [[-30, 4], [0, 4], [15, -2]] },
      { points: [[-30, 4], [0, 0], [15, -2]] },
      { points: [[-30, 4], [0, -2], [15, -2]] },
    ],
  },
};

/** The server's refraction example: air over glass, 30° in and 19.5° out. */
const REFRACTION = {
  type: "rays",
  x_min: -2.2,
  x_max: 2.2,
  y_min: -2.2,
  y_max: 2.2,
  angles: [
    { vertex: [0, 0], start_deg: 90, end_deg: 120, label: "30°" },
    { vertex: [0, 0], start_deg: -90, end_deg: -70.53, label: "19.5°", role: "result", arrow: true },
  ],
  optics: {
    element: "interface",
    rays: [{ points: [[-1, 1.732], [0, 0], [0.667, -1.886]] }],
    media: ["air", "glass"],
  },
};

describe("RayDiagram layout", () => {
  it("draws every ray through its traced points, with a head on each long visible segment", async () => {
    const { spec, paths, height, t } = await draw(LENS);
    const lines = paths.filter((path) => path.color === RAY && path.style === "stroke");
    const heads = paths.filter((path) => path.color === RAY && path.style === "fill");
    expect(lines).toHaveLength(3);
    expect(heads).toHaveLength(3);
    spec.optics.rays.forEach((ray, index) => {
      const points = ray.points.map((p) => toScreen(p.x, p.y, t));
      expect(asPoints(lines[index].d)).toEqual(points);
      const marks = rayMarks(points, { x: 0, y: 0, width: WIDTH, height });
      expect(marks.length).toBeGreaterThan(0);
      // A filled head per mark: base, tip, base, close.
      expect(heads[index].d).toHaveLength(marks.length * 4);
      marks.forEach((mark, m) => {
        expect(heads[index].d[m * 4 + 1]).toEqual(["L", mark.x, mark.y]);
      });
    });
  });

  it("stands a lens on the axis across every ray it meets, its heads out for converging", async () => {
    const { spec, paths, height, t } = await draw(LENS);
    const element = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 2);
    expect(element).toBeDefined();
    const x = toScreen(0, 0, t).px;
    const extent = elementExtent(spec.optics, spec.bounds, t, height);
    expect(element!.d.slice(0, 2)).toEqual([
      ["M", x, extent.top],
      ["L", x, extent.bottom],
    ]);
    const hits = spec.optics.rays.flatMap((ray) => ray.points.filter((p) => p.x === 0)).map((p) => toScreen(0, p.y, t).py);
    expect(extent.top).toBeLessThan(Math.min(...hits));
    expect(extent.bottom).toBeGreaterThan(Math.max(...hits));
    // Open heads at both ends: the top one points up, away from the axis.
    const [, , topBarb, topTip, , bottomBarb, bottomTip] = element!.d;
    expect(topTip).toEqual(["L", x, extent.top]);
    expect(topBarb[2]).toBeGreaterThan(extent.top);
    expect(bottomTip).toEqual(["L", x, extent.bottom]);
    expect(bottomBarb[2]).toBeLessThan(extent.bottom);
    expect(element!.d).toHaveLength(8);
  });

  it("turns a diverging lens's heads in", async () => {
    const { paths, t, spec, height } = await draw({ ...LENS, optics: { ...LENS.optics, element: "diverging_lens" } });
    const element = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 2)!;
    const extent = elementExtent(spec.optics, spec.bounds, t, height);
    expect(element.d[2][2]).toBeLessThan(extent.top);
    expect(element.d[5][2]).toBeGreaterThan(extent.bottom);
  });

  it("labels the object past its tip and an inverted image below its tip", async () => {
    const { labels, t, axis } = await draw(LENS);
    const object = label(labels, "object");
    const objectTip = toScreen(-30, 4, t);
    expect(object.y).toBeLessThan(objectTip.py);
    expect(object.x + object.width / 2).toBeCloseTo(objectTip.px, 6);
    const image = label(labels, "image");
    const imageTip = toScreen(15, -2, t);
    expect(imageTip.py).toBeGreaterThan(axis);
    expect(labelBox(image).y).toBeGreaterThan(imageTip.py);
    expect(image.x + image.width / 2).toBeCloseTo(imageTip.px, 6);
  });

  it("ticks each focal point and labels it under the axis, over it where a ray crosses", async () => {
    const { paths, labels, t, axis } = await draw(LENS);
    const focus = [-10, 10].map((x) => toScreen(x, 0, t).px);
    const ticks = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 1.5);
    expect(ticks!.d).toEqual(focus.flatMap((px) => [["M", px, axis - 4], ["L", px, axis + 4]]));
    const marks = labels.filter((item) => item.text === FOCUS);
    expect(marks).toHaveLength(2);
    marks.forEach((mark, index) => expect(mark.x + mark.width / 2).toBeCloseTo(focus[index], 6));
    expect(labelBox(marks[0]).y).toBeGreaterThan(axis);
    // The ray refracted through the far focus runs just under the axis there.
    expect(labelBox(marks[1]).y + labelBox(marks[1]).height).toBeLessThan(axis);
  });

  it.each([
    ["the lens", LENS],
    ["the refraction", REFRACTION],
    ["a concave mirror", { ...LENS, optics: { ...LENS.optics, element: "concave_mirror", image: undefined } }],
  ])("keeps every label in %s off the rays and off each other", async (_name, fence) => {
    const { spec, labels, t } = await draw(fence as Record<string, unknown>);
    const rays = spec.optics.rays.flatMap((ray) =>
      polylineSegments(ray.points.map((p) => toScreen(p.x, p.y, t))),
    );
    expect(labels.length).toBeGreaterThan(1);
    for (const item of labels) expect(labelHits(item, rays, 0)).toBe(false);
    labels.forEach((a, i) =>
      labels.slice(i + 1).forEach((b) => expect(overlaps(labelBox(a), labelBox(b))).toBe(false)),
    );
  });

  it("moves a label to its next spot when a ray crosses the first", async () => {
    const below = { points: [[-34, -3], [0, -3]] };
    const plain = await draw({
      ...LENS,
      optics: { ...LENS.optics, object: { x: -20, height: 2, label: "A" }, image: undefined, rays: [below] },
    });
    const tip = toScreen(-20, 2, plain.t);
    expect(label(plain.labels, "A").y).toBeLessThan(tip.py);
    // A level ray 10 px over the tip runs through the spot above it.
    const blocked = await draw({
      ...LENS,
      optics: {
        ...LENS.optics,
        object: { x: -20, height: 2, label: "A" },
        image: undefined,
        rays: [below, { points: [[-34, 2 + 10 / plain.t.scale], [0, 2 + 10 / plain.t.scale]] }],
      },
    });
    const moved = label(blocked.labels, "A");
    expect(moved.x).toBeCloseTo(tip.px + 5, 6);
  });

  it("draws a concave mirror's face leaning toward the light, hatched behind", async () => {
    const { paths, t } = await draw({ ...LENS, optics: { ...LENS.optics, element: "concave_mirror" } });
    const x = toScreen(0, 0, t).px;
    const face = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 2)!;
    expect(face.d).toHaveLength(25);
    const points = asPoints(face.d);
    expect(points[0].px).toBeLessThan(x);
    expect(points[24].px).toBeLessThan(x);
    expect(points[12].px).toBeCloseTo(x, 6);
    // The axis is the first thin tertiary stroke; the hatching is the second.
    const hatch = paths.filter((path) => path.color === lightTheme.textTertiary && path.strokeWidth === 1 && !path.dash)[1];
    expect(hatch!.d.length).toBeGreaterThan(10);
    for (let i = 0; i < hatch!.d.length; i += 2) {
      expect(hatch!.d[i + 1][1]).toBeGreaterThan(hatch!.d[i][1]);
    }
  });

  it("lays an interface across the canvas and names each medium away from its ray", async () => {
    const { paths, labels, axis } = await draw(REFRACTION);
    const boundary = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 1.5);
    expect(boundary!.d).toEqual([["M", 0, axis], ["L", WIDTH, axis]]);
    const air = label(labels, "air");
    const glass = label(labels, "glass");
    // The incoming ray is on the left above, the refracted one on the right below.
    expect(air.x + air.width).toBeCloseTo(WIDTH - 8, 6);
    expect(labelBox(air).y + labelBox(air).height).toBeLessThan(axis);
    expect(glass.x).toBeCloseTo(8, 6);
    expect(labelBox(glass).y).toBeGreaterThan(axis);
  });

  it("draws each angle's arc at its vertex, the answer bold and arrowed", async () => {
    const { paths, labels, t } = await draw(REFRACTION);
    const centre = toScreen(0, 0, t);
    const given = paths.find((path) => path.color === lightTheme.textSecondary && path.strokeWidth === 1.5 && path.d.length > 2 && path.d[0][1] !== 0);
    const result = paths.find((path) => path.color === lightTheme.primary && path.strokeWidth === 2);
    expect(given).toBeDefined();
    expect(result).toBeDefined();
    for (const [, px, py] of given!.d.slice(0, 6)) {
      expect(Math.hypot(px - centre.px, py - centre.py)).toBeCloseTo(26, 6);
    }
    // The result's arc ends in an open arrowhead (three more commands).
    expect(result!.d.length).toBe(Math.max(6, Math.ceil(19.47 / 6)) + 1 + 3);
    expect(label(labels, "30°")).toBeDefined();
    expect(label(labels, "19.5°")).toBeDefined();
  });

  it("dashes a virtual image's shaft and keeps its head solid", async () => {
    const { paths, t, axis } = await draw({
      ...LENS,
      optics: {
        ...LENS.optics,
        element: "diverging_lens",
        image: { x: -6.67, height: 1.33, label: "image", virtual: true },
        rays: [...LENS.optics.rays, { points: [[0, 4], [-10, 0]], virtual: true }],
      },
    });
    const image = paths.filter((path) => path.color === lightTheme.primary);
    const shaft = image.find((path) => path.dash);
    expect(shaft!.dash).toEqual([4, 3]);
    const x = toScreen(-6.67, 0, t).px;
    expect(shaft!.d[0]).toEqual(["M", x, axis]);
    expect(image.filter((path) => path.style === "fill")).toHaveLength(1);
    const virtual = paths.filter((path) => path.dash?.[0] === 4 && path.dash[1] === 4 && path.strokeWidth === 1);
    expect(virtual.length).toBeGreaterThan(0);
  });

  it("draws a measure at its world length with its label beside it", async () => {
    const fence = {
      ...LENS,
      vectors: [{ anchor: [-30, -3], dx: 30, dy: 0, label: "u = 30 cm", role: "measure" }],
    };
    const { paths, labels, t, height } = await draw(fence);
    const expected = layoutMeasure(
      { anchor: { x: -30, y: -3 }, dx: 30, dy: 0, label: "u = 30 cm" },
      t,
      { width: WIDTH, height },
      measureDiagramText,
    );
    const shaft = paths.find((path) => path.dash?.[0] === 3);
    expect(shaft!.d).toEqual([["M", expected.from.px, expected.from.py], ["L", expected.to.px, expected.to.py]]);
    expect(label(labels, "u = 30 cm")).toEqual(expected.label);
  });
});
