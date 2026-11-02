/**
 * Pins what `WaveDiagram` draws for a standing wave on a string, the same wave
 * in a pipe, and a travelling wave: every Skia primitive with its paint, each
 * path as its commands (positions to 0.1 px), and every label. Reduce Motion
 * is on, so the curve is the first frame and a standing wave shows its
 * envelope.
 */
import { render } from "@testing-library/react-native";

import { PhysicsDiagram } from "@/components/rich/diagrams/PhysicsDiagram";

jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotion: () => true,
  useReduceMotionSetting: () => true,
}));

jest.mock("@shopify/react-native-skia", () => {
  const actual = jest.requireActual("@shopify/react-native-skia");
  const named = (name: string) => {
    const Primitive = () => null;
    Primitive.displayName = name;
    return Primitive;
  };
  const round = (value: number) => Math.round(value * 10) / 10 || 0;
  const makePath = () => {
    const ops: string[] = [];
    const path = {
      ops,
      moveTo: (x: number, y: number) => ops.push(`M${round(x)},${round(y)}`) && path,
      lineTo: (x: number, y: number) => ops.push(`L${round(x)},${round(y)}`) && path,
      addRect: (r: { x: number; y: number; width: number; height: number }) =>
        ops.push(`R${round(r.x)},${round(r.y)},${round(r.width)},${round(r.height)}`) && path,
      addCircle: (x: number, y: number, r: number) =>
        ops.push(`C${round(x)},${round(y)},${round(r)}`) && path,
      close: () => ops.push("Z") && path,
    };
    return path;
  };
  const font = {
    measureText: (text: string) => ({ width: Array.from(text).length * 6.6 }),
    getGlyphIDs: (text: string) => Array.from(text).map((char) => char.codePointAt(0)),
    getGlyphWidths: (ids: number[]) => ids.map(() => 6.6),
  };
  return {
    ...actual,
    Path: named("Path"),
    Circle: named("Circle"),
    DashPathEffect: named("DashPathEffect"),
    Text: named("Text"),
    Skia: {
      ...actual.Skia,
      Path: { Make: makePath },
      XYWHRect: (x: number, y: number, width: number, height: number) => ({ x, y, width, height }),
    },
    useFont: () => font,
  };
});

type Fiber = {
  type: unknown;
  memoizedProps: Record<string, unknown>;
  child: Fiber | null;
  sibling: Fiber | null;
  return: Fiber | null;
};

const PRIMITIVES = new Set(["Group", "Path", "Circle", "Text", "HaloText", "PlaybackButton"]);
const OPAQUE = new Set(["PlaybackButton"]);

function valueText(value: unknown): string {
  if (typeof value === "number") return String(Math.round(value * 10) / 10 || 0);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `[${value.map(valueText).join(",")}]`;
  if (value && typeof value === "object") {
    if ("ops" in value) return (value as { ops: string[] }).ops.join(" ") || "empty";
    if ("value" in value) return valueText((value as { value: unknown }).value);
    return `{${Object.entries(value)
      .filter(([, entry]) => typeof entry !== "function")
      .map(([key, entry]) => `${key}:${valueText(entry)}`)
      .join(",")}}`;
  }
  return String(value);
}

function typeName(type: unknown): string | undefined {
  if (typeof type === "string") return type;
  const named = type as { displayName?: string; name?: string } | null;
  return named?.displayName ?? named?.name;
}

function primitiveText(name: string, props: Record<string, unknown>): string {
  const words = Object.entries(props)
    .filter(([key, value]) => key !== "children" && key !== "font" && typeof value !== "function")
    .map(([key, value]) => `${key}=${valueText(value)}`);
  const child = props.children as { type: unknown; props: Record<string, unknown> } | undefined;
  if (name === "Path" && child && typeof child === "object" && "type" in child) {
    words.push(`${typeName(child.type)}=${valueText(child.props.intervals)}`);
  }
  return `${name} ${words.join(" ")}`;
}

function lines(fiber: Fiber | null, depth: number, out: string[]) {
  for (let node = fiber; node; node = node.sibling) {
    const props = node.memoizedProps ?? {};
    const name = typeName(node.type);
    let line: string | null = null;
    if (typeof node.type === "string") {
      const style = props.style as { opacity?: number; width?: number } | undefined;
      const hidden = style?.opacity === 0 && style.width === 1;
      if (hidden && props.testID) line = `marker ${String(props.testID)}`;
      else if (node.type === "Text" && typeof props.children === "string") line = `Text "${props.children}"`;
      else if (props.testID || props.accessibilityLabel) {
        line = `${node.type} ${[props.testID, props.accessibilityLabel].filter(Boolean).join(" ")}`;
      }
    } else if (name && PRIMITIVES.has(name)) {
      line = primitiveText(name, props);
    }
    if (line) out.push(`${" ".repeat(depth)}${line}`);
    if (!OPAQUE.has(name ?? "")) lines(node.child, line ? depth + 1 : depth, out);
  }
}

async function drawn(spec: unknown): Promise<string> {
  const view = await render(<PhysicsDiagram content={JSON.stringify(spec)} kind="wave" />);
  let top = view.root?.unstable_fiber as Fiber | null | undefined;
  while (top?.return) top = top.return;
  const out: string[] = [];
  lines(top ?? null, 0, out);
  return out.join("\n");
}

const X = Array.from({ length: 41 }, (_, i) => i * 0.03);
const STANDING = {
  type: "wave",
  title: "Standing Wave",
  x_min: -0.05,
  x_max: 1.25,
  y_min: -0.12,
  y_max: 0.12,
  vectors: [{ anchor: [0, -0.09], dx: 0.8, dy: 0, label: "λ = 0.8 m", role: "measure" }],
  wave: {
    x: X,
    frames: Array.from({ length: 12 }, (_, f) =>
      X.map((x) => 0.05 * Math.cos((2 * Math.PI * f) / 12) * Math.sin((2 * Math.PI * x) / 0.8)),
    ),
    nodes: [0, 0.4, 0.8, 1.2],
    antinodes: [0.2, 0.6, 1.0],
    ends: ["fixed", "fixed"],
  },
};
const PIPE = { ...STANDING, wave: { ...STANDING.wave, ends: ["closed", "open"] } };
const TRAVELLING = {
  type: "wave",
  title: "Wave",
  x_min: 0,
  x_max: 6,
  y_min: -0.9,
  y_max: 0.9,
  wave: {
    x: Array.from({ length: 31 }, (_, i) => i * 0.2),
    frames: Array.from({ length: 8 }, (_, f) =>
      Array.from({ length: 31 }, (_, i) => 0.5 * Math.sin(2 * Math.PI * ((i * 0.2) / 1.5 - f / 8))),
    ),
  },
};

describe("WaveDiagram render", () => {
  it.each([
    ["a standing wave on a string", STANDING],
    ["a standing wave in a pipe", PIPE],
    ["a travelling wave", TRAVELLING],
  ])("draws %s as before", async (_name, spec) => {
    expect(await drawn(spec)).toMatchSnapshot();
  });
});
