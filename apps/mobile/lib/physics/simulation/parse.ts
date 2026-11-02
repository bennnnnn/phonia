/** Reading a `simulation` fence into a `SimulationSpec`. */
import {
  SCENE_TITLE_KEYS,
  type SceneTitleKey,
  type SimulationAngle,
  type SimulationArrow,
  type SimulationBody,
  type SimulationBodyShape,
  type SimulationKind,
  type SimulationPlanet,
  type SimulationPulley,
  type SimulationSolid,
  type SimulationSpec,
  type SimulationTether,
  type SimulationVector,
  type SimulationVectorRole,
} from "@/lib/physics/simulation/spec";
import {
  codePoints,
  finiteNumber,
  guard,
  optionalList,
  optionalText,
  readPoint,
  refuse,
  requirePoint,
} from "@/lib/fenceValidate";
import { isJsonRecord } from "@/lib/jsonFence";

const VECTOR_ROLES: readonly SimulationVectorRole[] = ["force", "result", "measure", "motion"];

const MAX_BODIES = 4;
const MAX_PATH_POINTS = 500;
const ARROW_KINDS: readonly SimulationArrow[] = [
  "gravity",
  "velocity",
  "centripetal",
  "normal",
  "friction",
];
/** Every body scene this build draws (a circuit, rays and a wave are `diagramKind`'s). */
export const SCENE_KINDS: readonly SimulationKind[] = [
  "projectile_motion",
  "orbit",
  "collision",
  "incline",
  "lever",
  "free_body",
  "vector_sum",
  "spring",
  "pendulum",
];
const MAX_VECTORS = 6;
/** Each of tethers, angles and solids, as the server caps them. */
const MAX_PARTS = 4;
const MAX_SHORT_LABEL = 24;
const MAX_ALT = 300;
const MIN_STROBE = 2;
const MAX_STROBE = 12;

/**
 * A field added in v2 that does not read. Old fields keep their old, lenient
 * reading so a stored reply renders exactly as before; a new field is as
 * strict as the server model, since anything it would refuse is a bug.
 */

function isIndex(raw: unknown): raw is number {
  return typeof raw === "number" && Number.isInteger(raw) && raw >= 0;
}

function parseVector(raw: unknown): SimulationVector | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const dx = finiteNumber(row.dx);
  const dy = finiteNumber(row.dy);
  if (dx === null || dy === null || (dx === 0 && dy === 0)) return null;
  const anchor = readPoint(row.anchor);
  if (!anchor) return null;
  // Range-checked against the bodies once they are all read.
  const body =
    row.body === undefined || row.body === null
      ? undefined
      : isIndex(row.body)
        ? row.body
        : refuse();
  return {
    anchor,
    dx,
    dy,
    label: typeof row.label === "string" && row.label ? row.label.slice(0, 24) : undefined,
    // An unknown role is drawn as a plain force: the arrow still says
    // something true about direction, and a newer server never blanks a scene.
    role: VECTOR_ROLES.includes(row.role as SimulationVectorRole)
      ? (row.role as SimulationVectorRole)
      : "force",
    ...(body !== undefined ? { body } : {}),
  };
}


function parsePath(raw: unknown): number[][] | null {
  if (!Array.isArray(raw) || raw.length < 2 || raw.length > MAX_PATH_POINTS) return null;
  const out: number[][] = [];
  for (const pair of raw) {
    if (!Array.isArray(pair) || pair.length !== 2) return null;
    const x = finiteNumber(pair[0]);
    const y = finiteNumber(pair[1]);
    if (x === null || y === null) return null;
    out.push([x, y]);
  }
  return out;
}

function parseBody(raw: unknown): SimulationBody | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const path = parsePath(row.path);
  if (!path) return null;
  const radius = finiteNumber(row.radius);
  const shape: SimulationBodyShape =
    row.shape === undefined
      ? "circle"
      : row.shape === "circle" || row.shape === "box"
        ? row.shape
        : refuse();
  return {
    label: typeof row.label === "string" && row.label ? row.label.slice(0, 32) : undefined,
    // A non-positive radius would draw nothing at all, so it falls back rather
    // than rendering an invisible body.
    radius: radius !== null && radius > 0 ? radius : 0.4,
    path,
    role: row.role === "secondary" ? "secondary" : "primary",
    shape,
  };
}

function parseTether(raw: unknown): SimulationTether {
  if (!isJsonRecord(raw) || !isIndex(raw.body)) refuse();
  return { anchor: requirePoint(raw.anchor), body: raw.body };
}

function parsePulley(raw: unknown): SimulationPulley | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (!isJsonRecord(raw)) refuse();
  const radius = finiteNumber(raw.radius);
  if (radius === null || radius <= 0) refuse();
  return { centre: requirePoint(raw.centre), radius };
}

function parsePlanet(raw: unknown): SimulationPlanet | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (!isJsonRecord(raw)) refuse();
  const radius = finiteNumber(raw.radius);
  if (radius === null || radius <= 0) refuse();
  const label = optionalText(raw.label, MAX_SHORT_LABEL);
  return label ? { radius, label } : { radius };
}

function parseAngle(raw: unknown): SimulationAngle {
  if (!isJsonRecord(raw)) refuse();
  const startDeg = finiteNumber(raw.start_deg);
  const endDeg = finiteNumber(raw.end_deg);
  if (startDeg === null || endDeg === null || startDeg === endDeg) refuse();
  const arrow =
    raw.arrow === undefined ? false : typeof raw.arrow === "boolean" ? raw.arrow : refuse();
  const role =
    raw.role === undefined
      ? "given"
      : raw.role === "given" || raw.role === "result"
        ? raw.role
        : refuse();
  const label = optionalText(raw.label, MAX_SHORT_LABEL);
  return {
    vertex: requirePoint(raw.vertex),
    startDeg,
    endDeg,
    arrow,
    role,
    ...(label ? { label } : {}),
  };
}

function parseSolid(raw: unknown): SimulationSolid {
  if (!isJsonRecord(raw) || !Array.isArray(raw.rect) || raw.rect.length !== 4) refuse();
  const [xMin, yMin, xMax, yMax] = raw.rect.map(finiteNumber);
  if (xMin === null || yMin === null || xMax === null || yMax === null) refuse();
  if (xMax <= xMin || yMax <= yMin) refuse();
  const kind =
    raw.kind === undefined
      ? "solid"
      : raw.kind === "solid" || raw.kind === "fluid"
        ? raw.kind
        : refuse();
  const label = optionalText(raw.label, MAX_SHORT_LABEL);
  return { rect: { xMin, yMin, xMax, yMax }, kind, ...(label ? { label } : {}) };
}

/** `arrow_labels`: only arrows the scene names, each a short string. */
function parseArrowLabels(
  raw: unknown,
  named: readonly unknown[],
): Partial<Record<SimulationArrow, string>> {
  if (raw === undefined) return {};
  if (!isJsonRecord(raw)) refuse();
  const out: Partial<Record<SimulationArrow, string>> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (!ARROW_KINDS.includes(key as SimulationArrow) || !named.includes(key)) refuse();
    if (typeof value !== "string" || codePoints(value) > MAX_SHORT_LABEL) refuse();
    if (value) out[key as SimulationArrow] = value;
  }
  return out;
}

function parseStrobe(raw: unknown): number | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (!isIndex(raw) || raw < MIN_STROBE || raw > MAX_STROBE) refuse();
  return raw;
}

function parseTitleKey(raw: unknown): SceneTitleKey | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (typeof raw !== "string") refuse();
  // A key this build does not know only means a newer server named the scene:
  // the English `title` still says what it is, so the scene draws under it.
  return SCENE_TITLE_KEYS.includes(raw as SceneTitleKey) ? (raw as SceneTitleKey) : undefined;
}

/**
 * Read a scene, or return null so the block can show its fallback.
 *
 * Deliberately as strict as the server model: this fence is server-owned, so
 * anything that does not parse is a bug or an invention, and neither should
 * reach the screen as a half-drawn animation. A circuit, a ray diagram and a
 * wave are not body scenes and read as null here; `diagramKind` routes them.
 */
export function parseSimulationSpec(raw: string): SimulationSpec | null {
  let data: unknown;
  try {
    data = JSON.parse(raw.trim());
  } catch {
    return null;
  }
  if (!data || typeof data !== "object") return null;
  return guard(() => readScene(data as Record<string, unknown>));
}

function readScene(row: Record<string, unknown>): SimulationSpec | null {
  if (!SCENE_KINDS.includes(row.type as SimulationKind)) return null;
  const bodies = readBodies(row.bodies);
  if (!bodies) return null;

  const xMin = finiteNumber(row.x_min);
  const xMax = finiteNumber(row.x_max);
  const yMin = finiteNumber(row.y_min);
  const yMax = finiteNumber(row.y_max);
  if (xMin === null || xMax === null || yMin === null || yMax === null) return null;
  if (xMax <= xMin || yMax <= yMin) return null;

  const namedArrows = Array.isArray(row.arrows) ? row.arrows : [];
  const arrows = namedArrows.filter((a) =>
    ARROW_KINDS.includes(a as SimulationArrow),
  ) as SimulationArrow[];

  const centre = readPoint(row.centre) ?? undefined;
  const vectors = readVectors(row.vectors);
  if (!vectors) return null;
  // A scene with neither is an empty box; one or the other makes it a picture.
  if (bodies.length === 0 && vectors.length === 0) return null;

  const beam = readBeam(row.beam);
  const pivot = beam ? (readPoint(row.pivot) ?? undefined) : undefined;
  const anchor = readPoint(row.anchor) ?? undefined;
  // A spring with no wall would start the coil at the canvas edge, which is
  // not the spring the solver sampled.
  if (row.type === "spring" && (anchor === undefined || bodies.length !== 1)) return null;

  const inclineDeg = finiteNumber(row.incline_deg);

  const parts = readParts(row, namedArrows, bodies, vectors, centre);
  if (!parts) return null;
  const usable = usableArrows(arrows, centre, inclineDeg);
  const shownLabels: Partial<Record<SimulationArrow, string>> = {};
  for (const kind of usable) {
    const label = parts.arrowLabels[kind];
    if (label) shownLabels[kind] = label;
  }

  return {
    type: row.type as SimulationKind,
    title: typeof row.title === "string" && row.title ? row.title.slice(0, 64) : undefined,
    bodies,
    xMin,
    xMax,
    yMin,
    yMax,
    arrows: usable,
    centre,
    ground: row.ground === true,
    inclineDeg: inclineDeg ?? undefined,
    vectors,
    beam,
    pivot,
    anchor,
    ...parts,
    arrowLabels: shownLabels,
  };
}

/** The bodies, or null when one does not read or they are out of step. */
function readBodies(raw: unknown): SimulationBody[] | null {
  const rawBodies = Array.isArray(raw) ? raw : [];
  if (rawBodies.length > MAX_BODIES) return null;
  const bodies: SimulationBody[] = [];
  for (const entry of rawBodies) {
    const body = parseBody(entry);
    if (!body) return null;
    bodies.push(body);
  }
  // One clock drives every body, so unequal sample counts would put a
  // two-body scene out of step — a collision shown at the wrong moment.
  if (new Set(bodies.map((b) => b.path.length)).size > 1) return null;
  return bodies;
}

function readVectors(raw: unknown): SimulationVector[] | null {
  const rawVectors = Array.isArray(raw) ? raw : [];
  if (rawVectors.length > MAX_VECTORS) return null;
  const vectors: SimulationVector[] = [];
  for (const entry of rawVectors) {
    const vector = parseVector(entry);
    if (!vector) return null;
    vectors.push(vector);
  }
  return vectors;
}

function readBeam(raw: unknown): SimulationSpec["beam"] {
  let beam: SimulationSpec["beam"];
  if (Array.isArray(raw) && raw.length === 4) {
    const ends = raw.map(finiteNumber);
    if (ends.every((v) => v !== null)) {
      beam = { x1: ends[0]!, y1: ends[1]!, x2: ends[2]!, y2: ends[3]! };
    }
  }
  return beam;
}

/** The v2 fields, each left out of the fence when unused; null when one hangs on nothing. */
function readParts(
  row: Record<string, unknown>,
  namedArrows: readonly unknown[],
  bodies: readonly SimulationBody[],
  vectors: readonly SimulationVector[],
  centre: { x: number; y: number } | undefined,
) {
  const tethers = optionalList(row.tethers, MAX_PARTS).map(parseTether);
  const pulley = parsePulley(row.pulley);
  const centralBody = parsePlanet(row.central_body);
  const angles = optionalList(row.angles, MAX_PARTS).map(parseAngle);
  const solids = optionalList(row.solids, MAX_PARTS).map(parseSolid);
  const arrowLabels = parseArrowLabels(row.arrow_labels, namedArrows);
  const strobe = parseStrobe(row.strobe);
  const alt = optionalText(row.alt, MAX_ALT);
  const titleKey = parseTitleKey(row.title_key);

  // A string or an arrow riding on a body the scene does not have would be
  // drawn from nowhere.
  const attached = [
    ...tethers.map((tether) => tether.body),
    ...vectors.flatMap((vector) => (vector.body === undefined ? [] : [vector.body])),
  ];
  if (attached.some((index) => index >= bodies.length)) return null;
  // The planet sits at the centre; with no centre it has nowhere to be.
  if (centralBody && !centre) return null;
  // A pendulum is its bob and its string, or it is a ball floating in space.
  if (row.type === "pendulum" && (bodies.length !== 1 || tethers.length === 0)) return null;
  return { tethers, pulley, centralBody, angles, solids, arrowLabels, strobe, alt, titleKey };
}

/**
 * The named arrows the scene can draw. Each is read off something it may not
 * have: "toward the centre" needs a centre, and the normal and friction
 * directions come off the slope rather than the motion — a block that has not
 * started moving has no tangent to read them from. An arrow drawn without its
 * reference points somewhere confidently wrong, which is worse than no arrow.
 */
function usableArrows(
  arrows: readonly SimulationArrow[],
  centre: { x: number; y: number } | undefined,
  inclineDeg: number | null,
): SimulationArrow[] {
  return arrows.filter(
    (a) =>
      (a !== "centripetal" || centre !== undefined) &&
      ((a !== "normal" && a !== "friction") || inclineDeg !== null),
  );
}
