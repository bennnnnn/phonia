/**
 * Display-only pairing of a SMILES fence with the following molecule3d fence.
 *
 * Persist still stores both fences (server appends ```molecule3d after
 * ```smiles). The markdown preprocessor collapses an adjacent closed pair
 * into one ```molecule JSON fence so the UI mounts a single card.
 */
import { parseChemistryFence, readSmiles } from "@/lib/chemistry/fence";
import { fenceIdForLang } from "@/lib/fenceRegistry";
import { scanFences, type FenceSpan } from "@/lib/mdFenceScan";

type MoleculeFence = {
  smiles: string;
  caption: string | null;
  sdf: string | null;
};

type Fence = FenceSpan & { lang: string };

/** The language token of a fence's info string, lower-cased. */
function fenceLang(info: string): string {
  return (info.split(/\s+/, 1)[0] ?? "").toLowerCase();
}

function iterFences(text: string): Fence[] {
  return scanFences(text).map((fence) => ({ ...fence, lang: fenceLang(fence.info) }));
}

function isChemLang(lang: string): boolean {
  return fenceIdForLang(lang) === "chemistry";
}

function isMol3dLang(lang: string): boolean {
  return fenceIdForLang(lang) === "molecule3d";
}

function encodeMoleculeFence(payload: MoleculeFence): string {
  const row: Record<string, string> = { smiles: payload.smiles };
  if (payload.caption) row.caption = payload.caption;
  if (payload.sdf) row.sdf = payload.sdf;
  return `\`\`\`molecule\n${JSON.stringify(row)}\n\`\`\``;
}

/**
 * Replace a closed ```smiles / ```chemistry fence immediately followed by a
 * closed ```molecule3d (whitespace only in between) with one ```molecule fence.
 * Open/unclosed 3D tails are left alone so streaming still shows 2D-only.
 */
export function collapseAdjacentMoleculeFences(text: string): string {
  const fences = iterFences(text);
  if (fences.length < 2) return text;
  const parts: string[] = [];
  let cursor = 0;
  let i = 0;
  while (i < fences.length) {
    const chem = fences[i];
    const next = fences[i + 1];
    if (
      chem &&
      next &&
      chem.closed &&
      next.closed &&
      isChemLang(chem.lang) &&
      isMol3dLang(next.lang) &&
      text.slice(chem.end, next.start).trim() === ""
    ) {
      const parsed = parseChemistryFence(chem.body);
      if (parsed) {
        parts.push(text.slice(cursor, chem.start));
        const payload: MoleculeFence = { smiles: parsed.smiles, caption: parsed.caption, sdf: null };
        const sdfBody = next.body.trim();
        if (sdfBody) payload.sdf = sdfBody;
        parts.push(encodeMoleculeFence(payload));
        cursor = next.end;
        i += 2;
        continue;
      }
    }
    i += 1;
  }
  if (cursor === 0) return text;
  parts.push(text.slice(cursor));
  return parts.join("");
}

/**
 * After pairing, drop leftover ```molecule3d fences. The model still emits
 * its own 3D fence under a "3D Structure" heading even though the server
 * already appended one after ```smiles — that second card is empty.
 * Standalone molecule3d (no ```molecule in the message) is left alone.
 */
export function dropRedundantMolecule3dFences(text: string): string {
  const fences = iterFences(text);
  const hasCombined = fences.some((fence) => fence.lang === "molecule" && fence.closed);
  if (!hasCombined) return text;
  const parts: string[] = [];
  let cursor = 0;
  let dropped = false;
  for (const fence of fences) {
    if (!fence.closed || !isMol3dLang(fence.lang)) continue;
    const before = text.slice(cursor, fence.start);
    parts.push(before.replace(/(?:\n|^)#{1,6}[ \t]+(?:2D|3D)[ \t]+Structure[^\n]*\s*$/i, "\n"));
    cursor = fence.end;
    dropped = true;
  }
  if (!dropped) return text;
  parts.push(text.slice(cursor));
  return parts.join("").replace(/\n{3,}/g, "\n\n");
}

export function parseMoleculeFence(content: string): MoleculeFence | null {
  const trimmed = content.trim();
  if (trimmed.startsWith("{")) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return null;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const row = parsed as Record<string, unknown>;
    // The same gate a ```smiles fence goes through: this string reaches the drawer too.
    const smiles = typeof row.smiles === "string" ? readSmiles(row.smiles) : null;
    if (!smiles) return null;
    const caption = typeof row.caption === "string" ? row.caption.trim() : "";
    const sdf = typeof row.sdf === "string" ? row.sdf.trim() : "";
    return { smiles, caption: caption || null, sdf: sdf || null };
  }
  const chem = parseChemistryFence(content);
  if (!chem) return null;
  return { smiles: chem.smiles, caption: chem.caption, sdf: null };
}
