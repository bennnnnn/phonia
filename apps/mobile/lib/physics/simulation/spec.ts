/** A `simulation` scene as the phone holds it once `parse.ts` has read the fence. */

export type SimulationArrow = "gravity" | "velocity" | "centripetal" | "normal" | "friction";

export type SimulationKind =
  | "projectile_motion"
  | "orbit"
  | "collision"
  | "incline"
  | "lever"
  | "free_body"
  | "vector_sum"
  | "spring"
  | "pendulum";

/**
 * An arrow the renderer cannot derive, so the solver states it.
 *
 * Every other arrow comes off the scene — velocity from the tangent,
 * centripetal from the centre, normal and friction from the slope — precisely
 * so it cannot disagree with what is drawn around it. These cannot be: the two
 * loads on a see-saw, the resultant of a 3 N and a 4 N force. The label
 * carries the magnitude the solver already computed, so the picture and the
 * answer pill cannot disagree either.
 */
export type SimulationVector = {
  anchor: { x: number; y: number };
  /**
   * How long these are on screen depends on the scene (`vectorScreenLengths`):
   * a vector-sum part or a `measure` is drawn at its true world length, and
   * every other vector is only *relative* — its direction, and a magnitude
   * compared with the other vectors of its kind in the same scene.
   */
  dx: number;
  dy: number;
  label?: string;
  /**
   * Visual weight only. `result` is the quantity the question asked for;
   * `measure` is an extent rather than a force — the h in mgh, the d in Fd —
   * drawn as a dimension line so it does not read as another arrow pushing;
   * `motion` is a kinematic arrow (an acceleration), drawn dashed with an
   * open head so it never reads as a force.
   */
  role: SimulationVectorRole;
  /**
   * The body this arrow rides on. `anchor` is then an offset from that body's
   * position, every frame: the tension on an Atwood mass goes where it goes.
   */
  body?: number;
};

export type SimulationVectorRole = "force" | "result" | "measure" | "motion";

export type SimulationBodyShape = "circle" | "box";

export type SimulationBody = {
  label?: string;
  radius: number;
  /** [x, y] world-unit samples, uniform in time. */
  path: number[][];
  role: "primary" | "secondary";
  /** A box is a square of side 2 * radius, turned onto the slope of an incline. */
  shape: SimulationBodyShape;
};

/** A taut string from a fixed point to a body: a pendulum, an Atwood rope. */
export type SimulationTether = { anchor: { x: number; y: number }; body: number };

/** The wheel an Atwood machine's rope runs over. */
export type SimulationPulley = { centre: { x: number; y: number }; radius: number };

/** The planet an orbit goes round, drawn at the scene's `centre` at true scale. */
export type SimulationPlanet = { radius: number; label?: string };

/**
 * An arc at a vertex, in degrees counter-clockwise from +x. With `arrow` it is
 * a curved arrow from `startDeg` to `endDeg`: a moment's turning sense.
 */
export type SimulationAngle = {
  vertex: { x: number; y: number };
  startDeg: number;
  endDeg: number;
  label?: string;
  arrow: boolean;
  role: "given" | "result";
};

/** A static rectangle: the table a ball rolls off, a cliff, a tank of water. */
export type SimulationSolid = {
  rect: { xMin: number; yMin: number; xMax: number; yMax: number };
  kind: "solid" | "fluid";
  label?: string;
};

/** Titles the client translates: `rich.scene_title_<key>`. Mirrors the server's `TitleKey`. */
export const SCENE_TITLE_KEYS = [
  "projectile",
  "free_fall",
  "orbit",
  "satellite",
  "circular_motion",
  "collision",
  "recoil",
  "incline",
  "moments",
  "free_body",
  "height",
  "atwood",
  "forces",
  "spring",
  "pendulum",
  "circuit",
  "lens",
  "mirror",
  "refraction",
  "wave",
  "standing_wave",
  "buoyancy",
  "charges",
] as const;

export type SceneTitleKey = (typeof SCENE_TITLE_KEYS)[number];

export type SimulationSpec = {
  type: SimulationKind;
  title?: string;
  bodies: SimulationBody[];
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  arrows: SimulationArrow[];
  centre?: { x: number; y: number };
  ground: boolean;
  /** Slope in degrees, descending left to right. Fixes normal and friction. */
  inclineDeg?: number;
  vectors: SimulationVector[];
  /** A rigid beam as its two ends, in world coords. */
  beam?: { x1: number; y1: number; x2: number; y2: number };
  pivot?: { x: number; y: number };
  /** Fixed end of a spring, in world coords. The coil is drawn from here. */
  anchor?: { x: number; y: number };
  tethers: SimulationTether[];
  pulley?: SimulationPulley;
  centralBody?: SimulationPlanet;
  angles: SimulationAngle[];
  solids: SimulationSolid[];
  /** A short label at the tip of a derived arrow: `{ velocity: "v" }`. */
  arrowLabels: Partial<Record<SimulationArrow, string>>;
  /** Faint copies of each body at this many evenly spaced samples. */
  strobe?: number;
  /** One sentence a screen reader says for the picture, instead of the generated one. */
  alt?: string;
  titleKey?: SceneTitleKey;
};
