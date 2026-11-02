import { mapPointW, nearestTraceSampleW } from "@/lib/math/graphWorklets";
import { NO_TRACE, traceTickW, type TraceTickState } from "@/lib/math/traceTicks";

const BOUNDS = { xMin: -6, xMax: 6, yMin: -6, yMax: 6 };
const WIDTH = 360;
const HEIGHT = 360;
const PAD = 16;
/** The explorer's default density: one sample per 0.06 x across this view. */
const SAMPLES = 200;

function curve(f: (x: number) => number, color = "#000") {
  const points = Array.from({ length: SAMPLES + 1 }, (_, i) => {
    const x = BOUNDS.xMin + ((BOUNDS.xMax - BOUNDS.xMin) * i) / SAMPLES;
    return [x, f(x)] as [number, number];
  });
  return { visible: true, color, points };
}

/** A finger dragged along x at 60 fps, holding to the first curve; ticks played per frame. */
function scrub(
  series: ReturnType<typeof curve>[],
  from: number,
  to: number,
  frames: number,
  follow: (x: number) => number,
): { ticks: number; changes: number } {
  let state: TraceTickState = NO_TRACE;
  let ticks = 0;
  let changes = 0;
  let previous = -1;
  for (let frame = 0; frame <= frames; frame += 1) {
    const x = from + ((to - from) * frame) / frames;
    const { px, py } = mapPointW(x, follow(x), BOUNDS, WIDTH, HEIGHT, PAD);
    const sample = nearestTraceSampleW(series, px, py, BOUNDS, WIDTH, HEIGHT, PAD);
    const key = sample ? sample.seriesIndex * 1_000_000 + sample.index : -1;
    if (key >= 0 && key !== previous) changes += 1;
    previous = key;
    const next = traceTickW(state, sample, (frame * 1000) / 60);
    state = next.state;
    if (next.tick) ticks += 1;
  }
  return { ticks, changes };
}

describe("trace haptics", () => {
  it("does not tick on every sample of a one-second scrub", () => {
    const line = (x: number) => 0.5 * x + 2;
    const { ticks, changes } = scrub([curve(line)], -2, 4, 60, line);
    // Each frame lands on a new sample: one tick per frame was a continuous buzz.
    expect(changes).toBe(61);
    expect(ticks).toBe(1);
  });

  it("ticks when it takes hold of the curve and at each root and the vertex", () => {
    const parabola = (x: number) => x * x - 4;
    // Grab at x = −3, the root at −2, the vertex at 0, the root at 2.
    expect(scrub([curve(parabola)], -3, 3, 60, parabola).ticks).toBe(4);
  });

  it("does not count turning the finger back as a turning point", () => {
    const line = (x: number) => x + 1;
    let state: TraceTickState = NO_TRACE;
    let ticks = 0;
    const indices = [130, 131, 132, 133, 132, 131, 130];
    indices.forEach((index, frame) => {
      const x = BOUNDS.xMin + ((BOUNDS.xMax - BOUNDS.xMin) * index) / SAMPLES;
      const next = traceTickW(state, { seriesIndex: 0, index, y: line(x) }, frame * 200);
      state = next.state;
      if (next.tick) ticks += 1;
    });
    expect(ticks).toBe(1);
  });

  it("ticks when the finger moves to another curve", () => {
    let state: TraceTickState = NO_TRACE;
    const ticks = [
      { seriesIndex: 0, index: 10, y: 1 },
      { seriesIndex: 0, index: 11, y: 1.1 },
      { seriesIndex: 1, index: 11, y: 3 },
    ].map((sample, frame) => {
      const next = traceTickW(state, sample, frame * 16);
      state = next.state;
      return next.tick;
    });
    expect(ticks).toEqual([true, false, true]);
  });

  it("lets two roots a frame apart share one tick", () => {
    const wave = (x: number) => Math.sin(40 * x);
    const { ticks } = scrub([curve(wave)], -1, 1, 60, wave);
    // 26 roots crossed in one second; never more than one tick per 90 ms.
    expect(ticks).toBeLessThanOrEqual(1 + Math.ceil(1000 / 90));
  });
});
