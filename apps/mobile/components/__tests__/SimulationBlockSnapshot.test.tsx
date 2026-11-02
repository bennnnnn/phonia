/**
 * Pins what `SimulationBlock` draws for one small scene of each kind (the ones
 * `simulationLayoutSnapshot.test.ts` lays out), so a change to the picture
 * shows up as a reviewed snapshot diff. A circuit, a ray diagram and a wave
 * are `PhysicsDiagram`'s: given one, this block shows its fallback line.
 *
 * Skia is the repo's mock with each primitive named, paths recorded and a font
 * loaded. A path is kept as its command counts and bounding box (`^` when it
 * is the one the line above drew); positions are rounded to the pixel and
 * other numbers to 0.01; the hidden test markers are listed by ID. Reduce
 * Motion is on, so each scene is drawn at its first frame.
 */
import { render } from "@testing-library/react-native";

import { SimulationBlock } from "@/components/rich/SimulationBlock";
import { SIMULATION_SCENES } from "@/lib/__tests__/fixtures/simulationScenes";

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
  const makePath = () => {
    const ops: (string | number)[][] = [];
    const path = {
      ops,
      moveTo: (x: number, y: number) => ops.push(["M", x, y]) && path,
      lineTo: (x: number, y: number) => ops.push(["L", x, y]) && path,
      close: () => ops.push(["Z"]) && path,
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
    Skia: { ...actual.Skia, Path: { Make: makePath } },
    useFont: () => font,
  };
});

const DIAGRAMS = {
  circuit: {
    type: "circuit",
    circuit: { source: { kind: "battery", label: "5 V" }, load: { part: "resistor" } },
  },
  rays: { type: "rays", optics: { element: "converging_lens", focal: 10 } },
  wave: { type: "wave", wave: { x: [0, 1, 2], frames: [[0, 1, 0]] } },
};

/** Drawn as one line each; HaloText and PlaybackButton keep their insides to themselves. */
const PRIMITIVES = new Set(["Group", "Path", "Circle", "HaloText", "PlaybackButton"]);
const OPAQUE = new Set(["HaloText", "PlaybackButton"]);
const HOST_PROPS = ["testID", "accessible", "accessibilityRole", "accessibilityLabel", "name"];
const SKIPPED_PROPS = new Set(["children", "font", "fallbacks"]);
const POSITIONS = new Set(["x", "y", "cx", "cy", "c", "r"]);
const SHORT: Record<string, string> = {
  strokeWidth: "w",
  strokeJoin: "join",
  strokeCap: "cap",
  accessibilityRole: "role",
  accessibilityLabel: "label",
};

type Fiber = {
  type: unknown;
  memoizedProps: Record<string, unknown>;
  child: Fiber | null;
  sibling: Fiber | null;
  return: Fiber | null;
};

const round = (value: number, digits = 2) => Math.round(value * 10 ** digits) / 10 ** digits || 0;

function pathText(ops: (string | number)[][]): string {
  if (ops.length === 0) return "empty";
  const counts = new Map<string, number>();
  for (const [command] of ops) counts.set(String(command), (counts.get(String(command)) ?? 0) + 1);
  const points = ops.filter((op) => op.length === 3) as [string, number, number][];
  const xs = points.map((op) => round(op[1], 0));
  const ys = points.map((op) => round(op[2], 0));
  const box = `${Math.min(...xs)},${Math.min(...ys)} ${Math.max(...xs)},${Math.max(...ys)}`;
  return `${[...counts].map(([command, count]) => `${command}${count}`).join("")}[${box}]`;
}

function valueText(value: unknown, digits = 2): string {
  if (typeof value === "number") return String(round(value, digits));
  if (Array.isArray(value)) return `[${value.map((entry) => valueText(entry, digits)).join(",")}]`;
  if (value && typeof value === "object") {
    if ("ops" in value) return pathText((value as { ops: (string | number)[][] }).ops);
    // A shared or derived value: what it holds this frame.
    if ("value" in value) return valueText((value as { value: unknown }).value, digits);
    return `{${Object.entries(value)
      .map(([key, entry]) => `${key}:${valueText(entry, digits)}`)
      .join(",")}}`;
  }
  return String(value);
}

function typeName(type: unknown): string | undefined {
  if (typeof type === "string") return type;
  const named = type as { displayName?: string; name?: string } | null;
  return named?.displayName ?? named?.name;
}

/** The path or text first, then its paint; a dash the path holds goes last. */
function primitiveText(name: string, props: Record<string, unknown>, previous: unknown): string {
  const words = Object.entries(props)
    .filter(([key, value]) => !SKIPPED_PROPS.has(key) && typeof value !== "function")
    .map(([key, value]) => {
      if (key === "path" && value === previous) return "^";
      return key === "path" || key === "text" || key === "color" || key === "style"
        ? valueText(value)
        : `${SHORT[key] ?? key}=${valueText(value, POSITIONS.has(key) ? 0 : 2)}`;
    });
  const child = props.children as { type: unknown; props: Record<string, unknown> } | undefined;
  if (name === "Path" && child && typeof child === "object" && "type" in child) {
    words.push(`${typeName(child.type)}=${valueText(child.props.intervals)}`);
  }
  return `${name} ${words.join(" ")}`;
}

function isMarker(props: Record<string, unknown>): boolean {
  const style = props.style as { opacity?: number; width?: number } | undefined;
  return style?.opacity === 0 && style.width === 1;
}

function hostText(type: string, props: Record<string, unknown>): string | null {
  if (type === "Text" && typeof props.children === "string") return `Text "${props.children}"`;
  const parts = HOST_PROPS.filter((key) => props[key] !== undefined).map(
    (key) => `${SHORT[key] ?? key}=${valueText(props[key])}`,
  );
  if (parts.length === 0) return null;
  const style = props.style as { width?: number; height?: number } | undefined;
  if (typeof style?.width === "number") {
    parts.push(`${round(style.width, 0)}x${round(style.height ?? 0, 0)}`);
  }
  return `${type} ${parts.join(" ")}`;
}

function lines(fiber: Fiber | null, depth: number, out: string[], markers: string[]) {
  let previous: unknown = null;
  for (let node = fiber; node; node = node.sibling) {
    const props = node.memoizedProps ?? {};
    const name = typeName(node.type);
    let line: string | null = null;
    if (typeof node.type === "string") {
      if (isMarker(props)) {
        if (props.testID) markers.push(String(props.testID).replace("simulation-", ""));
      } else {
        line = hostText(node.type, props);
      }
    } else if (name && PRIMITIVES.has(name)) {
      line = primitiveText(name, props, previous);
      previous = props.path;
    }
    if (line) out.push(`${" ".repeat(depth)}${line}`);
    if (!OPAQUE.has(name ?? "")) lines(node.child, line ? depth + 1 : depth, out, markers);
  }
}

async function drawn(content: string): Promise<string> {
  const view = await render(<SimulationBlock content={content} />);
  let top = view.root?.unstable_fiber as Fiber | null | undefined;
  while (top?.return) top = top.return;
  const out: string[] = [];
  const markers: string[] = [];
  lines(top ?? null, 0, out, markers);
  if (markers.length > 0) out.push(`markers: ${markers.join(" ")}`);
  return out.join("\n");
}

describe("SimulationBlock render", () => {
  it.each(Object.keys(SIMULATION_SCENES))("draws a %s scene as before", async (kind) => {
    const scene = SIMULATION_SCENES[kind as keyof typeof SIMULATION_SCENES];
    expect(await drawn(JSON.stringify(scene))).toMatchSnapshot();
  });

  it.each(Object.keys(DIAGRAMS))("leaves a %s to PhysicsDiagram", async (kind) => {
    expect(await drawn(JSON.stringify(DIAGRAMS[kind as keyof typeof DIAGRAMS]))).toMatchSnapshot();
  });
});
