/** Parse ```molecule3d / ```mol3d / ```3dmol fence bodies. */

const MAX_SDF_LENGTH = 50000;

/**
 * V2000 counts line: "  9  9  0  0  0  0  0  0  0  0999 V2000". Only digits and blanks sit
 * before the version tag; the fields are fixed-width, so they can run together.
 * V3000 blocks are not read: the native viewer only draws V2000.
 */
const COUNTS_LINE_RE = /^\s*\d[\d ]*V2000\s*$/;

type Molecule3DFence = {
  /** SDF (MOL block) string the native viewer reads. */
  sdf: string;
  caption: string | null;
};

/**
 * Extract an SDF/MOL block from fence content.
 * Supports an optional plain-text caption on preceding lines.
 *
 * An SDF block starts with a molecule title line, then a line with
 * counts (e.g. "  9  9  0  0  0  0  0  0  0  0999 V2000"), and ends
 * with "M  END". We detect the block by finding "M  END" and taking
 * everything from the line that looks like the counts line upward.
 */
export function parseMolecule3DFence(content: string): Molecule3DFence | null {
  const raw = content.trim();
  if (!raw) return null;

  // Find "M  END" — the SDF block terminator.
  const endIdx = raw.indexOf("M  END");
  if (endIdx === -1) return null;

  const block = raw.slice(0, endIdx + 6); // include "M  END"
  if (block.length > MAX_SDF_LENGTH) return null;

  // The caption is any text after "M  END" (or before the block if no
  // trailing text). In practice the model puts the caption first, then
  // the SDF. We take lines before the counts line as the caption.
  const lines = block.split("\n");
  // The counts line is the 4th line in a MOL block (1-indexed: title,
  // program/timestamp, comment, counts). But the model may not include
  // all 3 header lines, so find it by pattern.
  const countsLineIdx = lines.findIndex((line) => COUNTS_LINE_RE.test(line));
  if (countsLineIdx < 0) return null;

  // A V2000 MOL block has exactly 3 header lines before the counts line.
  // The backend used to prepend the formula (`O2\n` + RDKit molblock), which
  // shifted counts off line 4 and the viewer parsed 0 atoms — blank viewer.
  const headerStart = Math.max(0, countsLineIdx - 3);
  const prefix = lines
    .slice(0, headerStart)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const molLines = lines.slice(headerStart);
  const headerCount = countsLineIdx - headerStart;
  const padded =
    headerCount >= 3 ? molLines : [...Array<string>(3 - headerCount).fill(""), ...molLines];
  const sdf = `${padded.join("\n")}\n$$$$`;

  const trailing = raw.slice(endIdx + 6).trim();
  const title = padded[0]?.trim() || "";
  const caption = prefix[0] || trailing.split("\n")[0]?.trim() || title || null;

  return { sdf, caption };
}

export type MolAtom = { x: number; y: number; z: number; el: string };
type MolBond = { a: number; b: number; order: number };
export type MolGeometry = { atoms: MolAtom[]; bonds: MolBond[] };

const ATOM_LINE_RE =
  /^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+([A-Z][a-z]?)/;
const MAX_ATOMS = 400;
const FIELD_WIDTH = 3;

/**
 * Integer fields of a counts or bond line. MOL writes them as `%3d`, so "173172" is 173 and
 * 172 and " 1101" is 1 and 101; a hand-typed block separates them with blanks instead. A first
 * token wider than one field can only be fields that ran together.
 */
function readFields(line: string, count: number): number[] | null {
  const tokens = line.trim().split(/\s+/);
  const glued = (tokens[0] ?? "").length > FIELD_WIDTH;
  const fields = Array.from({ length: count }, (_, i) =>
    glued ? line.slice(i * FIELD_WIDTH, (i + 1) * FIELD_WIDTH).trim() : (tokens[i] ?? ""),
  );
  if (!fields.every((field) => /^\d+$/.test(field))) return null;
  return fields.map(Number);
}

/**
 * Read 3D atom positions and bonds from a V2000 MOL/SDF block.
 * Used by the native SVG viewer (WebGL is unreliable in WKWebView).
 */
export function parseMolGeometry(sdf: string): MolGeometry | null {
  const lines = sdf.split("\n");
  const countsIdx = lines.findIndex((line) => COUNTS_LINE_RE.test(line));
  if (countsIdx < 0) return null;
  const counts = readFields(lines[countsIdx]!, 2);
  if (!counts) return null;
  const [nAtoms, nBonds] = counts as [number, number];
  if (nAtoms < 1 || nAtoms > MAX_ATOMS) return null;

  const atoms: MolAtom[] = [];
  for (let i = 0; i < nAtoms; i++) {
    const line = lines[countsIdx + 1 + i];
    if (!line) return null;
    const m = line.match(ATOM_LINE_RE);
    if (!m) return null;
    atoms.push({ x: Number(m[1]), y: Number(m[2]), z: Number(m[3]), el: m[4]! });
  }

  const bonds: MolBond[] = [];
  for (let i = 0; i < nBonds; i++) {
    const line = lines[countsIdx + 1 + nAtoms + i];
    if (!line) break;
    const fields = readFields(line, 3);
    if (!fields) continue;
    const a = fields[0]! - 1;
    const b = fields[1]! - 1;
    const order = fields[2] || 1;
    if (a >= 0 && b >= 0 && a < nAtoms && b < nAtoms && a !== b) {
      bonds.push({ a, b, order });
    }
  }
  return { atoms, bonds };
}
