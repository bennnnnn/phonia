/**
 * The wave diagram's reading and frame stepping. The client never evaluates a
 * wave: it walks the server's frames and blends between neighbours.
 */
import {
  describeWave,
  isStandingWave,
  parseWaveSpec,
  sampleAt,
  waveCycleLength,
  waveEnvelope,
  waveHasPipe,
  waveSamplesAt,
  type WaveSpec,
} from "@/lib/physics/wave";

const X = Array.from({ length: 9 }, (_, i) => i * 0.15);

/** A third-harmonic standing wave, sampled the way the server does: one period, no repeat. */
function standing(frames = 24): Record<string, unknown> {
  return {
    x: X,
    frames: Array.from({ length: frames }, (_, f) =>
      X.map((x) => 0.05 * Math.cos((2 * Math.PI * f) / frames) * Math.sin((2 * Math.PI * x) / 0.8)),
    ),
    nodes: [0, 0.4, 0.8, 1.2],
    antinodes: [0.2, 0.6, 1.0],
    ends: ["fixed", "fixed"],
  };
}

/** A travelling wave: each frame shifted a little further right. */
function travelling(): Record<string, unknown> {
  return {
    x: X,
    frames: Array.from({ length: 4 }, (_, f) => X.map((x) => 0.5 * Math.sin(2 * Math.PI * (x / 1.5 - f / 4)))),
  };
}

function parse(raw: unknown): WaveSpec {
  const spec = parseWaveSpec(raw);
  if (!spec) throw new Error("expected the wave to parse");
  return spec;
}

describe("parseWaveSpec", () => {
  it("reads a standing wave with its marks and ends", () => {
    const spec = parse(standing());
    expect(spec.frames).toHaveLength(24);
    expect(spec.nodes).toEqual([0, 0.4, 0.8, 1.2]);
    expect(spec.ends).toEqual(["fixed", "fixed"]);
  });

  it("defaults a travelling wave's ends and marks", () => {
    const spec = parse(travelling());
    expect(spec.ends).toEqual(["none", "none"]);
    expect(spec.nodes).toEqual([]);
    expect(spec.antinodes).toEqual([]);
  });

  it.each([
    ["x samples that do not increase", { ...standing(), x: [...X.slice(0, 8), X[7]] }],
    ["one x sample", { ...standing(), x: [0], frames: [[0], [0]] }],
    ["161 x samples", { x: Array.from({ length: 161 }, (_, i) => i), frames: [Array(161).fill(0), Array(161).fill(0)] }],
    ["a frame one value short", { ...standing(), frames: [X.map(() => 0), X.slice(1).map(() => 0)] }],
    ["a frame with a null", { ...standing(), frames: [X.map(() => 0), X.map((_, i) => (i === 3 ? null : 0))] }],
    ["a single frame", { ...standing(), frames: [X.map(() => 0)] }],
    ["49 frames", standing(49)],
    ["an end nothing draws", { ...standing(), ends: ["fixed", "glued"] }],
    ["three ends", { ...standing(), ends: ["fixed", "fixed", "fixed"] }],
    ["thirteen nodes", { ...standing(), nodes: Array.from({ length: 13 }, (_, i) => i * 0.1) }],
    ["a node given as text", { ...standing(), nodes: ["0.4"] }],
    ["no frames", { x: X }],
    ["not an object", [X]],
  ])("refuses %s", (_name, raw) => {
    expect(parseWaveSpec(raw)).toBeNull();
  });
});

describe("stepping through the frames", () => {
  it("loops over every frame when the period is sampled without a repeat", () => {
    const spec = parse(standing());
    expect(waveCycleLength(spec.frames)).toBe(24);
  });

  it("drops a closing frame that repeats the first, so the loop does not stall", () => {
    const spec = parse(standing());
    const closed = [...spec.frames, spec.frames[0]];
    expect(waveCycleLength(closed)).toBe(24);
  });

  it("shows frame 0 at the start and again at the end of a loop", () => {
    const { frames } = parse(travelling());
    const cycle = waveCycleLength(frames);
    expect(waveSamplesAt(frames, cycle, 0)).toEqual(frames[0]);
    const end = waveSamplesAt(frames, cycle, 1);
    end.forEach((value, i) => expect(value).toBeCloseTo(frames[0][i], 9));
  });

  it("blends halfway between neighbouring frames", () => {
    const { frames } = parse(travelling());
    const cycle = waveCycleLength(frames);
    const halfway = waveSamplesAt(frames, cycle, 0.5 / cycle);
    halfway.forEach((value, i) => expect(value).toBeCloseTo((frames[0][i] + frames[1][i]) / 2, 9));
    // The last frame blends back into the first.
    const wrap = waveSamplesAt(frames, cycle, (cycle - 0.5) / cycle);
    wrap.forEach((value, i) => expect(value).toBeCloseTo((frames[cycle - 1][i] + frames[0][i]) / 2, 9));
  });
});

describe("wave marks", () => {
  it("takes the envelope as the largest displacement each sample reaches", () => {
    const spec = parse(standing());
    const envelope = waveEnvelope(spec);
    expect(envelope[0]).toBeCloseTo(0, 9);
    // x = 0.15 sits near an antinode at 0.2.
    expect(envelope[1]).toBeCloseTo(0.05 * Math.sin((2 * Math.PI * 0.15) / 0.8), 9);
    expect(sampleAt(spec.x, envelope, 0.075)).toBeCloseTo((envelope[0] + envelope[1]) / 2, 9);
    expect(sampleAt(spec.x, envelope, -1)).toBe(0);
  });

  it("tells a standing wave and a pipe from a travelling wave", () => {
    expect(isStandingWave(parse(standing()))).toBe(true);
    expect(isStandingWave(parse(travelling()))).toBe(false);
    expect(waveHasPipe(parse(standing()))).toBe(false);
    expect(waveHasPipe(parse({ ...standing(), ends: ["closed", "open"] }))).toBe(true);
  });

  it("describes the wave for a screen reader", () => {
    const t = (key: string, options?: Record<string, unknown>) =>
      options ? `${key}(${Object.values(options).join(",")})` : key;
    expect(describeWave(parse(standing()), ["λ = 0.8 m"], t)).toBe(
      "rich.diagram_a11y_standing_wave. rich.diagram_a11y_nodes(4). rich.diagram_a11y_antinodes(3). " +
        "rich.diagram_a11y_ends(rich.diagram_end_fixed, rich.diagram_end_fixed). λ = 0.8 m.",
    );
    expect(describeWave(parse(travelling()), [], t)).toBe("rich.diagram_a11y_wave.");
  });
});
