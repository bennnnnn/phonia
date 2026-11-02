export type RectangleSpec = {
  type: "rectangle" | "square";
  width: number;
  height: number;
  unit?: string;
  show_diagonal?: boolean;
  show_angle?: boolean;
  show_area?: boolean;
  show_perimeter?: boolean;
  /** School-diagram congruence ticks on equal sides (default on). */
  show_ticks?: boolean;
  diagonal?: number;
  angle_deg?: number;
  area?: number;
  perimeter?: number;
  labels?: Record<string, string>;
};

export type TriangleSpec = {
  type: "triangle";
  base: number;
  height: number;
  unit?: string;
  show_labels?: boolean;
  /** Congruence tick marks on equal legs (default on). */
  show_ticks?: boolean;
  /** Dashed altitude from apex to base (default on — already the height line). */
  show_altitude?: boolean;
  /** Interior vertex degrees (default on). */
  show_angle?: boolean;
  area?: number;
  labels?: Record<string, string>;
};

export type RightTriangleSpec = {
  type: "right_triangle";
  base: number;
  height: number;
  unit?: string;
  show_labels?: boolean;
  show_hypotenuse?: boolean;
  /** Interior vertex degrees, not only the 90° square (default on). */
  show_angle?: boolean;
  hypotenuse?: number;
  area?: number;
  labels?: Record<string, string>;
};

export type CircleSpec = {
  type: "circle";
  radius: number;
  unit?: string;
  show_labels?: boolean;
  show_diameter?: boolean;
  show_area?: boolean;
  show_circumference?: boolean;
  diameter?: number;
  area?: number;
  circumference?: number;
  labels?: Record<string, string>;
};

export type TriangleSidesSpec = {
  type: "triangle_sides";
  a: number;
  b: number;
  c: number;
  relative_lengths?: boolean;
  unit?: string;
  show_labels?: boolean;
  /** Congruence ticks on equal sides (default on when any sides match). */
  show_ticks?: boolean;
  /** Altitude from the apex (opp. side a) to side a (default on). */
  show_altitude?: boolean;
  /** Median from the apex to the midpoint of side a (default off; on for isosceles). */
  show_median?: boolean;
  show_angle?: boolean;
  area?: number;
  labels?: Record<string, string>;
};

export type TrapezoidSpec = {
  type: "trapezoid";
  top: number;
  bottom: number;
  height: number;
  unit?: string;
  show_labels?: boolean;
  show_angle?: boolean;
  area?: number;
  labels?: Record<string, string>;
};

export type ParallelogramSpec = {
  type: "parallelogram";
  base: number;
  height: number;
  side: number;
  unit?: string;
  show_labels?: boolean;
  show_angle?: boolean;
  show_perimeter?: boolean;
  area?: number;
  perimeter?: number;
  labels?: Record<string, string>;
};

export type SectorSpec = {
  type: "sector";
  radius: number;
  angle_deg: number;
  unit?: string;
  show_labels?: boolean;
  arc_length?: number;
  area?: number;
  labels?: Record<string, string>;
};

export type GeometrySpec =
  | RectangleSpec
  | TriangleSpec
  | RightTriangleSpec
  | CircleSpec
  | TriangleSidesSpec
  | TrapezoidSpec
  | ParallelogramSpec
  | SectorSpec;

const GEOMETRY_KIND_SET: Record<GeometrySpec["type"], true> = {
  rectangle: true,
  square: true,
  triangle: true,
  right_triangle: true,
  circle: true,
  triangle_sides: true,
  trapezoid: true,
  parallelogram: true,
  sector: true,
};

/** Every figure this build draws; a fence naming another is refused as an unknown kind. */
export const GEOMETRY_KINDS = Object.keys(GEOMETRY_KIND_SET);

/** Match backend `RectangleGeometryInput` / triangle inputs (`le=1_000_000`). */
export const MAX_GEOMETRY_DIMENSION = 1_000_000;
