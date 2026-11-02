import {
  type GeometrySpec,
  type CircleSpec,
  type ParallelogramSpec,
  type RectangleSpec,
  type RightTriangleSpec,
  type SectorSpec,
  type TrapezoidSpec,
  type TriangleSidesSpec,
  type TriangleSpec,
} from "@/lib/math/geometryTypes";

function formatMagnitude(value: number, digits: number, fixed: boolean): string {
  if (!Number.isFinite(value)) return "";
  if (!fixed && Object.is(value % 1, 0)) return String(value);
  return value.toFixed(digits);
}

function dimensionLabel(explicit: string | undefined, value: number, unit: string): string {
  return explicit ?? `${value} ${unit}`;
}

/**
 * Format a measurement the server already solved. An omitted value stays
 * blank — the diagram must not invent area, hypotenuse, or circumference.
 */
function measurementLabel(
  explicit: string | undefined,
  value: number | undefined,
  unit: string,
  suffix = "",
  digits = 2,
  fixed = false,
): string {
  if (explicit) return explicit;
  if (value === undefined || !Number.isFinite(value)) return "";
  const magnitude = formatMagnitude(value, digits, fixed);
  return magnitude ? `${magnitude} ${unit}${suffix}` : "";
}

export function computeRectangleLabels(spec: RectangleSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    width: spec.labels?.width ?? `${spec.width} ${unit}`,
    height: spec.labels?.height ?? `${spec.height} ${unit}`,
    side: spec.labels?.side ?? `${spec.width} ${unit}`,
    diagonal: measurementLabel(spec.labels?.diagonal, spec.diagonal, unit, "", 2, true),
    angle: spec.labels?.angle
      ?? (spec.angle_deg !== undefined && Number.isFinite(spec.angle_deg)
        ? `${spec.angle_deg.toFixed(1)}°`
        : ""),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 1),
    perimeter: measurementLabel(spec.labels?.perimeter, spec.perimeter, unit, "", 1),
  };
}

export function computeTriangleLabels(spec: TriangleSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    base: dimensionLabel(spec.labels?.base, spec.base, unit),
    height: dimensionLabel(spec.labels?.height, spec.height, unit),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 1),
  };
}

export function computeRightTriangleLabels(spec: RightTriangleSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    base: dimensionLabel(spec.labels?.base, spec.base, unit),
    height: dimensionLabel(spec.labels?.height, spec.height, unit),
    hypotenuse: measurementLabel(spec.labels?.hypotenuse, spec.hypotenuse, unit, "", 2),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 1),
    angle: spec.labels?.angle ?? "90°",
    angle_at_base: spec.labels?.angle_at_base ?? "",
    angle_at_height: spec.labels?.angle_at_height ?? "",
  };
}

export function computeCircleLabels(spec: CircleSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    radius: dimensionLabel(spec.labels?.radius, spec.radius, unit),
    diameter: measurementLabel(spec.labels?.diameter, spec.diameter, unit, "", 2),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 2, true),
    circumference: measurementLabel(spec.labels?.circumference, spec.circumference, unit, "", 2, true),
  };
}

export function computeTriangleSidesLabels(spec: TriangleSidesSpec): Record<string, string> {
  const angles = {
    angle_a: spec.labels?.angle_a ?? "",
    angle_b: spec.labels?.angle_b ?? "",
    angle_c: spec.labels?.angle_c ?? "",
  };
  if (spec.relative_lengths) {
    return { a: String(spec.a), b: String(spec.b), c: String(spec.c), area: "", ...angles };
  }
  const unit = spec.unit ?? "cm";
  return {
    a: spec.labels?.a ?? `${spec.a} ${unit}`,
    b: spec.labels?.b ?? `${spec.b} ${unit}`,
    c: spec.labels?.c ?? `${spec.c} ${unit}`,
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 2),
    ...angles,
  };
}

export function computeTrapezoidLabels(spec: TrapezoidSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    top: dimensionLabel(spec.labels?.top, spec.top, unit),
    bottom: dimensionLabel(spec.labels?.bottom, spec.bottom, unit),
    height: dimensionLabel(spec.labels?.height, spec.height, unit),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 1),
  };
}

export function computeParallelogramLabels(spec: ParallelogramSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    base: dimensionLabel(spec.labels?.base, spec.base, unit),
    height: dimensionLabel(spec.labels?.height, spec.height, unit),
    side: dimensionLabel(spec.labels?.side, spec.side, unit),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 1),
    perimeter: measurementLabel(spec.labels?.perimeter, spec.perimeter, unit, "", 1),
  };
}

export function computeSectorLabels(spec: SectorSpec): Record<string, string> {
  const unit = spec.unit ?? "cm";
  return {
    radius: dimensionLabel(spec.labels?.radius, spec.radius, unit),
    angle: spec.labels?.angle ?? `${spec.angle_deg}°`,
    arc_length: measurementLabel(spec.labels?.arc_length, spec.arc_length, unit, "", 2, true),
    area: measurementLabel(spec.labels?.area, spec.area, unit, "²", 2, true),
  };
}

function labelsFor(spec: GeometrySpec): Record<string, string> {
  switch (spec.type) {
    case "rectangle":
    case "square":
      return computeRectangleLabels(spec);
    case "triangle":
      return computeTriangleLabels(spec);
    case "right_triangle":
      return computeRightTriangleLabels(spec);
    case "circle":
      return computeCircleLabels(spec);
    case "triangle_sides":
      return computeTriangleSidesLabels(spec);
    case "trapezoid":
      return computeTrapezoidLabels(spec);
    case "parallelogram":
      return computeParallelogramLabels(spec);
    case "sector":
      return computeSectorLabels(spec);
  }
}

/** Screen-reader text for a diagram. Only strings the figure already shows. */
export function geometryFigureLabel(spec: GeometrySpec): string {
  if ("show_labels" in spec && spec.show_labels === false) return "";
  const labels = labelsFor(spec);
  const skip = new Set<string>();
  if (spec.type === "circle" && spec.show_diameter && labels.diameter) skip.add("radius");
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const [key, value] of Object.entries(labels)) {
    if (skip.has(key)) continue;
    const text = value.trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    parts.push(text);
  }
  return parts.join(", ");
}
