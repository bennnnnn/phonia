import type { MolAtom, MolGeometry } from "@/lib/chemistry/molecule3dFence";

export const MOLECULE_PREVIEW_HEIGHT = 280;

export type MoleculeStyle = "ball-stick" | "spacefill" | "wireframe";

const VIEW_PAD = 36;

type ElementLook = {
  /** CPK-style fill. */
  fill: string;
  /** Relative atomic size; the style scales it. */
  radius: number;
  /** The fill is light enough that its label must be dark. */
  lightFill?: boolean;
};

/** The one table for how an element is drawn. An element not in it gets the fallback below. */
const ELEMENTS: Record<string, ElementLook> = {
  H: { fill: "#c5cdd8", radius: 0.32, lightFill: true },
  Li: { fill: "#cc80ff", radius: 1.05 },
  B: { fill: "#ffb5b5", radius: 0.85, lightFill: true },
  C: { fill: "#3d3d3d", radius: 0.7 },
  N: { fill: "#3b6bdb", radius: 0.65 },
  O: { fill: "#e31c1c", radius: 0.6 },
  F: { fill: "#3aaa3a", radius: 0.5, lightFill: true },
  Na: { fill: "#ab5cf2", radius: 1.2 },
  Mg: { fill: "#8aff00", radius: 1.1, lightFill: true },
  Al: { fill: "#bfa6a6", radius: 1.05, lightFill: true },
  Si: { fill: "#f0c8a0", radius: 1.0, lightFill: true },
  P: { fill: "#e07000", radius: 0.9 },
  S: { fill: "#d4b41c", radius: 0.88, lightFill: true },
  Cl: { fill: "#1f9a1f", radius: 0.79, lightFill: true },
  K: { fill: "#8f40d4", radius: 1.4 },
  Ca: { fill: "#3dff00", radius: 1.25, lightFill: true },
  Mn: { fill: "#9c7ac7", radius: 1.0 },
  Fe: { fill: "#e06633", radius: 1.0 },
  Cu: { fill: "#c88033", radius: 0.95 },
  Zn: { fill: "#7d80b0", radius: 0.95 },
  Se: { fill: "#ffa100", radius: 1.0, lightFill: true },
  Br: { fill: "#a62929", radius: 0.94 },
  I: { fill: "#940094", radius: 1.15 },
};

const UNKNOWN: ElementLook = { fill: "#c45c9a", radius: 0.7 };

/** Near-black ink: the rim drawn around every atom, and the label on a light fill. */
export const ATOM_INK = "#1a1a1a";

function look(element: string): ElementLook {
  return ELEMENTS[element] ?? UNKNOWN;
}

export function atomColor(element: string): string {
  return look(element).fill;
}

export function atomLabelColor(element: string): string {
  return look(element).lightFill ? ATOM_INK : "#fff";
}

/** Stroke width of a bond line in this style. */
export function bondStrokeWidth(style: MoleculeStyle): number {
  return style === "wireframe" ? 1.6 : 3.4;
}

/** Ball-and-stick and wire always name the atom. Sphere style stays unlabeled. */
export function showsAtomLabel(style: MoleculeStyle): boolean {
  return style !== "spacefill";
}

function rotate(atom: MolAtom, center: Point3, yaw: number, pitch: number): Point3 {
  const ax = atom.x - center.x;
  const ay = atom.y - center.y;
  const az = atom.z - center.z;
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const x = ax * cosYaw + az * sinYaw;
  const z = -ax * sinYaw + az * cosYaw;
  const cosPitch = Math.cos(pitch);
  const sinPitch = Math.sin(pitch);
  return {
    x,
    y: ay * cosPitch - z * sinPitch,
    z: ay * sinPitch + z * cosPitch,
  };
}

type Point3 = { x: number; y: number; z: number };

/**
 * Where the camera looks and how far it must stand back: the middle of the un-rotated molecule
 * and the radius of the sphere that holds every atom. Rotation only turns the molecule about that
 * point, so nothing leaves the view and the scale never changes while it is dragged.
 */
function fitSphere(geometry: MolGeometry, atomScale: number): { center: Point3; radius: number } {
  const min = { x: Infinity, y: Infinity, z: Infinity };
  const max = { x: -Infinity, y: -Infinity, z: -Infinity };
  for (const atom of geometry.atoms) {
    min.x = Math.min(min.x, atom.x);
    max.x = Math.max(max.x, atom.x);
    min.y = Math.min(min.y, atom.y);
    max.y = Math.max(max.y, atom.y);
    min.z = Math.min(min.z, atom.z);
    max.z = Math.max(max.z, atom.z);
  }
  const center = {
    x: (min.x + max.x) / 2,
    y: (min.y + max.y) / 2,
    z: (min.z + max.z) / 2,
  };
  let radius = 0;
  for (const atom of geometry.atoms) {
    const reach =
      Math.hypot(atom.x - center.x, atom.y - center.y, atom.z - center.z) +
      look(atom.el).radius * atomScale;
    radius = Math.max(radius, reach);
  }
  return { center, radius: Math.max(radius, 0.4) };
}

type LaidOutAtom = {
  index: number;
  element: string;
  x: number;
  y: number;
  z: number;
  radius: number;
};

type LaidOutBond = {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

/** One thing to paint; the list is sorted back to front. */
type DrawItem = { kind: "atom"; index: number } | { kind: "bond"; index: number };

type MoleculeLayout = {
  atoms: LaidOutAtom[];
  /** Every line to draw; a double bond is two entries. Empty in the space-filling style. */
  bonds: LaidOutBond[];
  drawOrder: DrawItem[];
};

/** A bond's lines: one, or two or three side by side for a double or triple bond. */
function bondLines(
  first: LaidOutAtom,
  second: LaidOutAtom,
  order: number,
  bondIndex: number,
): LaidOutBond[] {
  const dx = second.x - first.x;
  const dy = second.y - first.y;
  const distance = Math.hypot(dx, dy) || 1;
  const copies = Math.min(3, Math.max(1, order));
  const spread = copies === 1 ? 0 : copies === 2 ? 3.2 : 4.2;
  return Array.from({ length: copies }, (_, copy) => {
    const shift = copies === 1 ? 0 : (copy - (copies - 1) / 2) * spread;
    const offsetX = (-dy / distance) * shift;
    const offsetY = (dx / distance) * shift;
    return {
      key: `${bondIndex}-${copy}`,
      x1: first.x + offsetX,
      y1: first.y + offsetY,
      x2: second.x + offsetX,
      y2: second.y + offsetY,
    };
  });
}

export function layoutMolecule(
  geometry: MolGeometry,
  yaw: number,
  pitch: number,
  width: number,
  height: number,
  style: MoleculeStyle,
): MoleculeLayout {
  const atomScale = style === "spacefill" ? 0.72 : style === "wireframe" ? 0.2 : 0.32;
  const { center, radius: reach } = fitSphere(geometry, atomScale);
  const span = Math.min(width, height) - VIEW_PAD * 2;
  // The padding is 36px on each side. A stage narrower than 72px has no positive scale.
  if (!(span > 0)) return { atoms: [], bonds: [], drawOrder: [] };
  const scale = span / (2 * reach);
  const atoms: LaidOutAtom[] = geometry.atoms.map((atom, index) => {
    const point = rotate(atom, center, yaw, pitch);
    return {
      index,
      element: atom.el,
      x: point.x * scale + width / 2,
      y: -point.y * scale + height / 2,
      z: point.z,
      radius: Math.max(3, look(atom.el).radius * scale * atomScale),
    };
  });

  // Painter's algorithm: each item sits at its depth, a bond halfway between its atoms, so a
  // bond runs behind the atom nearer the viewer and in front of the one farther away.
  const bonds: LaidOutBond[] = [];
  const items: { item: DrawItem; z: number }[] = atoms.map((atom) => ({
    item: { kind: "atom", index: atom.index },
    z: atom.z,
  }));
  if (style !== "spacefill") {
    geometry.bonds.forEach((bond, bondIndex) => {
      const first = atoms[bond.a];
      const second = atoms[bond.b];
      if (!first || !second) return;
      for (const line of bondLines(first, second, bond.order, bondIndex)) {
        items.push({ item: { kind: "bond", index: bonds.length }, z: (first.z + second.z) / 2 });
        bonds.push(line);
      }
    });
  }
  // At equal depth (a flat molecule) bonds go first, so an atom is drawn over the bond's end.
  const rank = (item: DrawItem) => (item.kind === "bond" ? 0 : 1);
  items.sort((left, right) => left.z - right.z || rank(left.item) - rank(right.item));
  return { atoms, bonds, drawOrder: items.map((entry) => entry.item) };
}
