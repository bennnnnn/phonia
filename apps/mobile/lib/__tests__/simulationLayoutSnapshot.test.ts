/**
 * Pins what `layoutSimulationScene` returns for one small scene of each kind,
 * so a change to the layout shows up as a reviewed snapshot diff.
 *
 * Numbers are rounded to 0.01 px, a polyline longer than eight points (an arc,
 * a rope) is kept as its length and ends, and the scene's own parts the layout
 * hands back unchanged (`vector`, `angle`, `solid`) are left out.
 */
import { SIMULATION_SCENES as SCENES } from "@/lib/__tests__/fixtures/simulationScenes";
import { layoutSimulationScene, parseSimulationSpec, simulationTransform, simulationViewportHeight } from "@/lib/physics/simulation";
import { type SimulationKind } from "@/lib/physics/simulation/spec";

const WIDTH = 312;
const FONT = 11;
const measure = (text: string) => text.length * 6.6;

function isPoint(value: unknown): boolean {
  return typeof value === "object" && value !== null && "px" in value && "py" in value;
}

const PASSED_THROUGH = new Set(["vector", "angle", "solid"]);

function compact(value: unknown): unknown {
  if (typeof value === "number") return Math.round(value * 100) / 100 || 0;
  if (Array.isArray(value)) {
    if (value.length > 8 && value.every(isPoint)) {
      const last = value[value.length - 1];
      return { points: value.length, first: compact(value[0]), last: compact(last) };
    }
    return value.map(compact);
  }
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !PASSED_THROUGH.has(key))
        .map(([key, entry]) => [key, compact(entry)]),
    );
  }
  return value;
}

describe("layoutSimulationScene", () => {
  it.each(Object.keys(SCENES) as SimulationKind[])("lays out a %s scene as before", (kind) => {
    const spec = parseSimulationSpec(JSON.stringify(SCENES[kind]));
    if (!spec) throw new Error(`${kind} fixture did not parse`);
    const height = simulationViewportHeight(spec, WIDTH, 24, 136, 240);
    const transform = simulationTransform(spec, WIDTH, height, 24);
    const layout = layoutSimulationScene(spec, transform, WIDTH, height, measure, FONT);
    const lines = Object.entries(layout).map(
      ([key, entry]) => `${key}: ${JSON.stringify(compact(entry))}`,
    );
    expect(lines.join("\n")).toMatchSnapshot();
  });
});
