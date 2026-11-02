/**
 * Reading a circuit, ray or wave fence: the common scene fields every diagram
 * shares (title, alt, bounds, measures, angles), then the kind's own object
 * through its parser in `lib/physics/`.
 *
 * No Skia here: the list placeholder imports this to size a cell before the
 * renderers load.
 */
import { type DiagramKind } from "@/lib/physics/diagramKind";
import { layoutCircuit, parseCircuitSpec, type CircuitSpec } from "@/lib/physics/circuit";
import {
  parseDiagramAngles,
  parseMeasureVectors,
  parseOpticsSpec,
  parseWorldBounds,
  worldViewportHeight,
  type DiagramAngle,
  type MeasureVector,
  type OpticsSpec,
  type WorldBounds,
} from "@/lib/physics/optics";
import { parseWaveSpec, type WaveSpec } from "@/lib/physics/wave";
import { measureDiagramText } from "@/components/rich/diagrams/textWidth";

type Header = {
  title?: string;
  /** Picks a translated title; the English `title` is its fallback. */
  titleKey?: string;
  /** One sentence a screen reader says for the picture. */
  alt?: string;
};

export type CircuitDiagramSpec = Header & { kind: "circuit"; circuit: CircuitSpec };
export type RayDiagramSpec = Header & {
  kind: "rays";
  bounds: WorldBounds;
  optics: OpticsSpec;
  angles: DiagramAngle[];
  measures: MeasureVector[];
};
export type WaveDiagramSpec = Header & {
  kind: "wave";
  bounds: WorldBounds;
  wave: WaveSpec;
  measures: MeasureVector[];
};
export type PhysicsDiagramSpec = CircuitDiagramSpec | RayDiagramSpec | WaveDiagramSpec;

const MAX_TITLE = 64;
const MAX_ALT = 300;
/**
 * A title key only chooses which translation to show, so a key this build
 * does not know falls back to the English title instead of blanking the
 * diagram. Anything that is not a plain key is still refused.
 */
const TITLE_KEY = /^[a-z][a-z0-9_]{0,39}$/;

/** The object each kind carries, and the one only it may carry. */
const FIELD: Record<DiagramKind, "circuit" | "optics" | "wave"> = {
  circuit: "circuit",
  rays: "optics",
  wave: "wave",
};

function text(value: unknown, max: number): string | undefined | null {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string" || [...value].length > max) return null;
  return value.length > 0 ? value : undefined;
}

/**
 * Read a diagram fence, or null so the block shows its fallback. As strict as
 * the server model: this fence is server-owned, so anything that does not
 * parse is a bug or an invention, and neither should reach the screen as half
 * a diagram.
 */
export function parsePhysicsDiagram(content: string, kind: DiagramKind): PhysicsDiagramSpec | null {
  let data: unknown;
  try {
    data = JSON.parse(content.trim());
  } catch {
    return null;
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const row = data as Record<string, unknown>;
  if (row.type !== kind) return null;
  for (const [other, field] of Object.entries(FIELD)) {
    const present = row[field] !== undefined && row[field] !== null;
    if (present !== (other === kind)) return null;
  }

  const title = text(row.title, MAX_TITLE);
  const alt = text(row.alt, MAX_ALT);
  if (title === null || alt === null) return null;
  let titleKey: string | undefined;
  if (row.title_key !== undefined && row.title_key !== null) {
    if (typeof row.title_key !== "string" || !TITLE_KEY.test(row.title_key)) return null;
    titleKey = row.title_key;
  }
  const bounds = parseWorldBounds(row);
  const measures = parseMeasureVectors(row.vectors);
  const angles = parseDiagramAngles(row.angles);
  if (!bounds || !measures || !angles) return null;
  // Validated as the server does, though a diagram never draws a body.
  if (row.bodies !== undefined && row.bodies !== null && !Array.isArray(row.bodies)) return null;
  const header: Header = { title, titleKey, alt };

  switch (kind) {
    case "circuit": {
      const circuit = parseCircuitSpec(row.circuit);
      return circuit ? { ...header, kind, circuit } : null;
    }
    case "rays": {
      const optics = parseOpticsSpec(row.optics);
      return optics ? { ...header, kind, bounds, optics, angles, measures } : null;
    }
    case "wave": {
      const wave = parseWaveSpec(row.wave);
      return wave ? { ...header, kind, bounds, wave, measures } : null;
    }
    default:
      return null;
  }
}

/** The canvas height a diagram takes at `width`, from the same layout the renderer uses. */
export function physicsDiagramCanvasHeight(spec: PhysicsDiagramSpec, width: number): number {
  if (spec.kind === "circuit") return layoutCircuit(spec.circuit, width, measureDiagramText).height;
  return worldViewportHeight(spec.bounds, width);
}

/** Only the wave moves, so only it has a play button under its canvas. */
export function physicsDiagramIsAnimated(spec: PhysicsDiagramSpec): boolean {
  return spec.kind === "wave";
}
