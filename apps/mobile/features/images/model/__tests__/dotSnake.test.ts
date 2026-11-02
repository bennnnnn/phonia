import {
  createDotSnake,
  type Direction,
  type DotSnake,
  nextDotSnakeMove,
  placeFood,
  resetDotSnake,
  sameCell,
  steerDotSnake,
  stepDotSnake,
} from "@/features/images/model/dotSnake";
import type { Cell } from "@/features/images/model/dotGrid";

const OPPOSITE: Record<Direction, Direction> = { up: "down", down: "up", left: "right", right: "left" };

/** Deterministic random in [0, 1) (mulberry32). */
function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const first = () => 0;

function snake(overrides: Partial<DotSnake> & { body: Cell[] }): DotSnake {
  return {
    cols: 8,
    rows: 8,
    direction: "right",
    food: null,
    target: null,
    startLength: overrides.body.length,
    maxLength: 12,
    ...overrides,
  };
}

const cells = (...pairs: [number, number][]): Cell[] => pairs.map(([x, y]) => ({ x, y }));

describe("createDotSnake", () => {
  it("lays the snake on the middle row heading right with food off its body", () => {
    const s = createDotSnake(6, 8, { random: first });
    expect(s.body).toEqual(cells([4, 4], [3, 4], [2, 4], [1, 4], [0, 4]));
    expect(s.direction).toBe("right");
    expect(s.food).toEqual({ x: 0, y: 0 });
    expect(s.target).toBeNull();
    expect(s.startLength).toBe(5);
  });

  it("fits the starting length to a narrow board and caps growth to a third of it", () => {
    const s = createDotSnake(3, 4, { length: 5, random: first });
    expect(s.body).toHaveLength(3);
    expect(s.maxLength).toBe(4);
  });
});

describe("stepDotSnake", () => {
  it("moves one cell toward the food and keeps its length", () => {
    const s = { ...createDotSnake(10, 9, { random: first }), food: { x: 8, y: 4 } };
    const next = stepDotSnake(s, first);
    expect(next.body[0]).toEqual({ x: 5, y: 4 });
    expect(next.body).toHaveLength(5);
    expect(next.direction).toBe("right");
  });

  it("turns toward food beside it", () => {
    const s = { ...createDotSnake(10, 9, { random: first }), food: { x: 4, y: 1 } };
    expect(stepDotSnake(s, first).body[0]).toEqual({ x: 4, y: 3 });
  });

  it("never reverses, even when the food is straight behind", () => {
    const s = { ...createDotSnake(10, 9, { random: first }), food: { x: 0, y: 2 } };
    const next = stepDotSnake(s, first);
    expect(next.direction).not.toBe("left");
    expect([3, 5]).toContain(next.body[0].y);
    expect(next.body[0].x).toBe(4);
  });

  it("grows by one on eating and puts new food on a free cell", () => {
    const s = snake({ body: cells([2, 2], [1, 2], [0, 2]), food: { x: 3, y: 2 } });
    const next = stepDotSnake(s, first);
    expect(next.body).toEqual(cells([3, 2], [2, 2], [1, 2], [0, 2]));
    expect(next.food).toEqual({ x: 0, y: 0 });
    expect(next.body.some((cell) => sameCell(cell, next.food as Cell))).toBe(false);
  });

  it("stops growing at its maximum length", () => {
    const s = snake({ body: cells([2, 2], [1, 2], [0, 2]), food: { x: 3, y: 2 }, maxLength: 3 });
    const next = stepDotSnake(s, first);
    expect(next.body).toEqual(cells([3, 2], [2, 2], [1, 2]));
  });

  it("turns away from a wall", () => {
    const s = snake({ body: cells([7, 3], [6, 3], [5, 3]), food: { x: 0, y: 0 } });
    const next = stepDotSnake(s, first);
    expect(next.direction).toBe("up");
    expect(next.body[0]).toEqual({ x: 7, y: 2 });
  });

  it("goes around its own body", () => {
    // Heading up with its own body ahead (2,1) and to the right (3,2).
    const s = snake({
      cols: 6,
      rows: 6,
      direction: "up",
      body: cells([2, 2], [2, 3], [3, 3], [3, 2], [3, 1], [2, 1], [1, 1]),
      food: { x: 3, y: 0 },
    });
    const next = stepDotSnake(s, first);
    expect(next.direction).toBe("left");
    expect(next.body[0]).toEqual({ x: 1, y: 2 });
  });

  it("may step onto the cell its tail is leaving", () => {
    const s = snake({
      cols: 2,
      rows: 2,
      direction: "up",
      body: cells([0, 1], [1, 1], [1, 0], [0, 0]),
      food: null,
    });
    expect(nextDotSnakeMove(s)).toEqual({ direction: "up", cell: { x: 0, y: 0 } });
  });

  it("comes out on the opposite edge when walls and body block every turn", () => {
    const s = snake({ cols: 4, rows: 1, body: cells([3, 0], [2, 0]), food: { x: 1, y: 0 } });
    const next = stepDotSnake(s, first);
    expect(next.body[0]).toEqual({ x: 0, y: 0 });
    expect(next.direction).toBe("right");
  });

  it("starts over instead of colliding when nothing is free", () => {
    const s = snake({
      cols: 3,
      rows: 3,
      direction: "up",
      startLength: 3,
      maxLength: 3,
      body: cells([0, 0], [1, 0], [2, 0], [2, 1], [1, 1], [0, 1], [0, 2], [1, 2], [2, 2]),
      food: null,
    });
    expect(nextDotSnakeMove(s)).toBeNull();
    const next = stepDotSnake(s, first);
    expect(next).toEqual(resetDotSnake(s, first));
    expect(next.body).toEqual(cells([2, 1], [1, 1], [0, 1]));
  });

  it("stays a valid snake over a long autopilot run", () => {
    const random = seeded(7);
    let s = createDotSnake(6, 8, { random });
    let eaten = 0;
    for (let i = 0; i < 3000; i += 1) {
      const before = s;
      const move = nextDotSnakeMove(before);
      // A real step (not a restart) never reverses.
      if (move) expect(move.direction).not.toBe(OPPOSITE[before.direction]);
      s = stepDotSnake(s, random);
      if (s.body.length > before.body.length) eaten += 1;
      const keys = s.body.map((cell) => `${cell.x},${cell.y}`);
      expect(new Set(keys).size).toBe(keys.length);
      for (const cell of s.body) {
        expect(cell.x).toBeGreaterThanOrEqual(0);
        expect(cell.x).toBeLessThan(6);
        expect(cell.y).toBeGreaterThanOrEqual(0);
        expect(cell.y).toBeLessThan(8);
      }
      expect(s.body.length).toBeGreaterThanOrEqual(s.startLength);
      expect(s.body.length).toBeLessThanOrEqual(s.maxLength);
      expect(s.food).not.toBeNull();
      expect(keys).not.toContain(`${s.food?.x},${s.food?.y}`);
    }
    expect(eaten).toBeGreaterThan(5);
  });
});

describe("steerDotSnake", () => {
  it("heads for the tapped cell, turning at most 90° a step, then back to the food", () => {
    let s: DotSnake = { ...createDotSnake(10, 9, { random: first }), food: { x: 9, y: 8 } };
    s = steerDotSnake(s, { x: 4, y: 0 });
    expect(s.target).toEqual({ x: 4, y: 0 });

    const directions: Direction[] = [s.direction];
    for (let i = 0; i < 4; i += 1) {
      s = stepDotSnake(s, first);
      directions.push(s.direction);
    }
    expect(s.body[0]).toEqual({ x: 4, y: 0 });
    expect(s.target).toBeNull();
    for (let i = 1; i < directions.length; i += 1) {
      expect(directions[i]).not.toBe(OPPOSITE[directions[i - 1]]);
    }

    // Target reached: autopilot turns right, toward the food.
    s = stepDotSnake(s, first);
    expect(["left", "right"]).toContain(s.direction);
    expect(s.body[0]).toEqual({ x: 5, y: 0 });
  });

  it("turns around a target straight behind instead of reversing", () => {
    let s = steerDotSnake(createDotSnake(10, 9, { random: first }), { x: 1, y: 4 });
    s = stepDotSnake(s, first);
    expect(s.direction).not.toBe("left");
    expect(s.body[0].x).toBe(4);
  });

  it("clamps a tap past the edge and clears the target when tapping the head", () => {
    const s = createDotSnake(6, 8, { random: first });
    expect(steerDotSnake(s, { x: 40, y: -3 }).target).toEqual({ x: 5, y: 0 });
    expect(steerDotSnake(s, s.body[0]).target).toBeNull();
  });
});

describe("placeFood", () => {
  it("picks among free cells only and returns null on a full board", () => {
    const body = cells([0, 0], [1, 0]);
    expect(placeFood(body, 2, 2, first)).toEqual({ x: 0, y: 1 });
    expect(placeFood(body, 2, 2, () => 0.99)).toEqual({ x: 1, y: 1 });
    expect(placeFood(cells([0, 0], [1, 0], [0, 1], [1, 1]), 2, 2, first)).toBeNull();
  });
});
