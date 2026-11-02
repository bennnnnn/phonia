/**
 * The dot game on the image-gen waiting card: a short snake of dots that
 * walks the grid one cell at a time toward a food dot.
 *
 * Pure grid logic: no React, no timers. Randomness (where new food lands) is
 * injected so tests are deterministic. There is no game over: when the snake
 * has nowhere left to go it starts again from its first position.
 *
 * Every step the snake keeps going or turns 90° (it never reverses). On its own
 * it heads for the food; a tap sets a `target` it heads for first.
 */
import type { Cell } from "@/features/images/model/dotGrid";

export type { Cell };

export type Direction = "up" | "down" | "left" | "right";

type Random = () => number;

export type DotSnake = {
  readonly cols: number;
  readonly rows: number;
  /** Head first, tail last. */
  readonly body: readonly Cell[];
  /** The way the head last moved. */
  readonly direction: Direction;
  /** `null` only on a board too small to hold one. */
  readonly food: Cell | null;
  /** Where a tap pointed. Cleared when the head gets there. */
  readonly target: Cell | null;
  readonly startLength: number;
  /** Eating past this length keeps the snake the same size. */
  readonly maxLength: number;
};

/** Time per step on screen. */
export const DOT_SNAKE_STEP_MS = 140;
const DOT_SNAKE_START_LENGTH = 5;
/** Long enough to feel like growth, short enough to stay calm on a small card. */
const DOT_SNAKE_MAX_LENGTH = 12;

const STEP: Record<Direction, Cell> = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};
const TURN_LEFT: Record<Direction, Direction> = {
  up: "left",
  left: "down",
  down: "right",
  right: "up",
};
const TURN_RIGHT: Record<Direction, Direction> = {
  up: "right",
  right: "down",
  down: "left",
  left: "up",
};

/** Unit vector of a direction, for drawing (e.g. which way the head looks). */
export function directionVector(direction: Direction): Cell {
  return STEP[direction];
}

export function sameCell(a: Cell, b: Cell): boolean {
  return a.x === b.x && a.y === b.y;
}

type CreateOptions = {
  length?: number;
  maxLength?: number;
  random?: Random;
};

/**
 * A fresh snake on the middle row, tail at the left edge, heading right, with
 * food on a random free cell.
 */
export function createDotSnake(cols: number, rows: number, options: CreateOptions = {}): DotSnake {
  const c = Math.max(1, Math.floor(cols));
  const r = Math.max(1, Math.floor(rows));
  const cells = c * r;
  const requested = Math.floor(options.length ?? DOT_SNAKE_START_LENGTH);
  // One row long at most, and always a free cell left for food.
  const startLength = Math.max(1, Math.min(requested, c, cells - 1));
  const maxLength = Math.max(
    startLength,
    Math.min(Math.floor(options.maxLength ?? DOT_SNAKE_MAX_LENGTH), Math.floor(cells / 3)),
  );
  const row = Math.floor(r / 2);
  const body: Cell[] = [];
  for (let x = startLength - 1; x >= 0; x -= 1) body.push({ x, y: row });
  return {
    cols: c,
    rows: r,
    body,
    direction: "right",
    food: placeFood(body, c, r, options.random ?? Math.random),
    target: null,
    startLength,
    maxLength,
  };
}

/** Start over at the first position, keeping the board and lengths. */
export function resetDotSnake(state: DotSnake, random: Random = Math.random): DotSnake {
  return createDotSnake(state.cols, state.rows, {
    length: state.startLength,
    maxLength: state.maxLength,
    random,
  });
}

/** Point the snake at a cell (a tap). Tapping the head clears the target. */
export function steerDotSnake(state: DotSnake, cell: Cell): DotSnake {
  const target = {
    x: clamp(Math.round(cell.x), 0, state.cols - 1),
    y: clamp(Math.round(cell.y), 0, state.rows - 1),
  };
  const head = state.body[0];
  return { ...state, target: head && sameCell(head, target) ? null : target };
}

type DotSnakeMove = { direction: Direction; cell: Cell };

/**
 * The next move, or `null` when every move collides. Candidates are straight
 * on, a left turn and a right turn. A move into a wall or the body is out;
 * when walls and body block all three, the snake may come out on the opposite
 * edge instead. Among the moves left it prefers one with room to keep going,
 * then the one closest to the target (or the food), then facing toward it,
 * then going straight.
 */
export function nextDotSnakeMove(state: DotSnake): DotSnakeMove | null {
  const head = state.body[0];
  if (!head) return null;
  const turns = [state.direction, TURN_LEFT[state.direction], TURN_RIGHT[state.direction]];

  const inside: DotSnakeMove[] = [];
  const wrapped: DotSnakeMove[] = [];
  for (const direction of turns) {
    const raw = add(head, STEP[direction]);
    if (inBounds(state, raw)) {
      if (!blocks(state, raw)) inside.push({ direction, cell: raw });
      continue;
    }
    const cell = { x: mod(raw.x, state.cols), y: mod(raw.y, state.rows) };
    if (!blocks(state, cell)) wrapped.push({ direction, cell });
  }
  const moves = inside.length > 0 ? inside : wrapped;
  if (moves.length === 0) return null;

  const goal = state.target ?? state.food;
  let best: DotSnakeMove | null = null;
  let bestScore: number[] = [];
  for (const move of moves) {
    const score = scoreMove(state, head, move, goal, turns.indexOf(move.direction));
    if (best == null || lexLess(score, bestScore)) {
      best = move;
      bestScore = score;
    }
  }
  return best;
}

/** Advance one cell: move, eat and grow, place new food, or start over. */
export function stepDotSnake(state: DotSnake, random: Random = Math.random): DotSnake {
  const move = nextDotSnakeMove(state);
  if (!move) return resetDotSnake(state, random);

  const eats = state.food != null && sameCell(move.cell, state.food);
  const grows = eats && state.body.length < state.maxLength;
  const body = [move.cell, ...(grows ? state.body : state.body.slice(0, -1))];
  const food = eats ? placeFood(body, state.cols, state.rows, random) : state.food;
  if (eats && food == null) return resetDotSnake(state, random);

  return {
    ...state,
    body,
    direction: move.direction,
    food,
    target: state.target && sameCell(move.cell, state.target) ? null : state.target,
  };
}

/** A random free cell, or `null` when the body covers the board. */
export function placeFood(
  body: readonly Cell[],
  cols: number,
  rows: number,
  random: Random,
): Cell | null {
  const taken = new Set(body.map(key));
  const free: Cell[] = [];
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      if (!taken.has(`${x},${y}`)) free.push({ x, y });
    }
  }
  if (free.length === 0) return null;
  const roll = random();
  const index = Number.isFinite(roll) ? Math.floor(roll * free.length) : 0;
  return free[clamp(index, 0, free.length - 1)];
}

// ── internals ────────────────────────────────────────────────────────────

/**
 * Lower is better: [no room to keep going, less room, distance to goal,
 * facing away from goal, turn order].
 */
function scoreMove(
  state: DotSnake,
  head: Cell,
  move: DotSnakeMove,
  goal: Cell | null,
  order: number,
): number[] {
  const body = bodyAfter(state, move.cell);
  const room = reachableCells(state, body);
  const roomy = room >= body.length ? 0 : 1;
  const distance = goal ? Math.abs(move.cell.x - goal.x) + Math.abs(move.cell.y - goal.y) : 0;
  const step = STEP[move.direction];
  const facing = goal ? step.x * (goal.x - head.x) + step.y * (goal.y - head.y) : 0;
  return [roomy, roomy ? -room : 0, distance, -facing, order];
}

function lexLess(a: number[], b: number[]): boolean {
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return a[i] < b[i];
  }
  return false;
}

function bodyAfter(state: DotSnake, cell: Cell): Cell[] {
  const grows =
    state.food != null && sameCell(cell, state.food) && state.body.length < state.maxLength;
  return [cell, ...(grows ? state.body : state.body.slice(0, -1))];
}

/** Whether moving onto `cell` hits the body. The tail moves away unless the snake grows. */
function blocks(state: DotSnake, cell: Cell): boolean {
  return bodyAfter(state, cell)
    .slice(1)
    .some((part) => sameCell(part, cell));
}

/** Free cells the head can reach from where it lands (flood fill, no wrap). */
function reachableCells(state: DotSnake, body: readonly Cell[]): number {
  const head = body[0];
  const taken = new Set(body.map(key));
  const seen = new Set<string>([key(head)]);
  const queue: Cell[] = [head];
  let count = 0;
  while (queue.length > 0) {
    const cell = queue.shift() as Cell;
    for (const direction of ["up", "down", "left", "right"] as const) {
      const next = add(cell, STEP[direction]);
      const id = key(next);
      if (!inBounds(state, next) || taken.has(id) || seen.has(id)) continue;
      seen.add(id);
      count += 1;
      queue.push(next);
    }
  }
  return count;
}

function add(a: Cell, b: Cell): Cell {
  return { x: a.x + b.x, y: a.y + b.y };
}

function inBounds(state: DotSnake, cell: Cell): boolean {
  return cell.x >= 0 && cell.y >= 0 && cell.x < state.cols && cell.y < state.rows;
}

function key(cell: Cell): string {
  return `${cell.x},${cell.y}`;
}

function mod(value: number, size: number): number {
  return ((value % size) + size) % size;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
