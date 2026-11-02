/** Parse a server-owned ```chem_scene fence. Invalid JSON draws nothing. */

import { isJsonRecord, parseJsonRecord } from "@/lib/jsonFence";

type BalanceRow = { element: string; left: number; right: number };

type BalanceScene = {
  kind: "balance";
  title: string;
  rows: BalanceRow[];
  charge: { left: number; right: number };
};

type StoichScene = {
  kind: "stoich";
  title: string;
  steps: { label: string; value: string }[];
};

type VseprScene = {
  kind: "vsepr";
  title: string;
  central: string;
  terminals: string[];
  lone_pairs: number;
  geometry: string;
  bond_angle: string;
  electron_geometry: string;
  ideal_angle: string;
};

type TitrationScene = {
  kind: "titration";
  title: string;
  region: string;
  anchors: { label: string; ph?: string; volume?: string; detail?: string; value?: string }[];
};

type EquilibriumScene = {
  kind: "equilibrium";
  title: string;
  rows: { species: string; initial: string; change: string; equilibrium: string }[];
};

type CellScene = {
  kind: "cell";
  title: string;
  anode: string;
  cathode: string;
  potential: string;
  electrons: string;
};

export type ChemistryScene =
  | BalanceScene
  | StoichScene
  | VseprScene
  | TitrationScene
  | EquilibriumScene
  | CellScene;

const SCENE_KIND_SET: Record<ChemistryScene["kind"], true> = {
  balance: true,
  stoich: true,
  vsepr: true,
  titration: true,
  equilibrium: true,
  cell: true,
};

/** Every chemistry scene this build draws; a fence naming another is refused as an unknown kind. */
export const CHEMISTRY_SCENE_KINDS = Object.keys(SCENE_KIND_SET);

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function whole(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function parseChemistryScene(content: string): ChemistryScene | null {
  const parsed = parseJsonRecord(content);
  if (!parsed) return null;
  const title = text(parsed.title);
  const kind = parsed.kind;
  if (!title || typeof kind !== "string") return null;
  if (kind === "balance") return parseBalance(parsed, title);
  if (kind === "stoich") return parseStoich(parsed, title);
  if (kind === "vsepr") return parseVsepr(parsed, title);
  if (kind === "titration") return parseTitration(parsed, title);
  if (kind === "equilibrium") return parseEquilibrium(parsed, title);
  if (kind === "cell") return parseCell(parsed, title);
  return null;
}

function parseBalance(parsed: Record<string, unknown>, title: string): BalanceScene | null {
  if (!Array.isArray(parsed.rows) || !isJsonRecord(parsed.charge)) return null;
  const rows: BalanceRow[] = [];
  for (const row of parsed.rows) {
    if (!isJsonRecord(row)) return null;
    const element = text(row.element);
    const left = whole(row.left);
    const right = whole(row.right);
    if (!element || left === null || right === null) return null;
    rows.push({ element, left, right });
  }
  const left = whole(parsed.charge.left);
  const right = whole(parsed.charge.right);
  if (!rows.length || left === null || right === null) return null;
  return { kind: "balance", title, rows, charge: { left, right } };
}

function parseStoich(parsed: Record<string, unknown>, title: string): StoichScene | null {
  if (!Array.isArray(parsed.steps)) return null;
  const steps: { label: string; value: string }[] = [];
  for (const step of parsed.steps) {
    if (!isJsonRecord(step)) return null;
    const label = text(step.label);
    const value = text(step.value);
    if (!label || !value) return null;
    steps.push({ label, value });
  }
  if (steps.length < 2) return null;
  return { kind: "stoich", title, steps };
}

function parseVsepr(parsed: Record<string, unknown>, title: string): VseprScene | null {
  const central = text(parsed.central);
  const geometry = text(parsed.geometry);
  const bondAngle = text(parsed.bond_angle);
  const electronGeometry = text(parsed.electron_geometry);
  const idealAngle = text(parsed.ideal_angle);
  const lonePairs = whole(parsed.lone_pairs);
  if (!central || !geometry || !bondAngle || !electronGeometry || !idealAngle || lonePairs === null) {
    return null;
  }
  if (!Array.isArray(parsed.terminals) || parsed.terminals.some((item) => typeof item !== "string")) {
    return null;
  }
  return {
    kind: "vsepr",
    title,
    central,
    terminals: parsed.terminals as string[],
    lone_pairs: lonePairs,
    geometry,
    bond_angle: bondAngle,
    electron_geometry: electronGeometry,
    ideal_angle: idealAngle,
  };
}

function parseTitration(parsed: Record<string, unknown>, title: string): TitrationScene | null {
  const region = text(parsed.region);
  if (!region || !Array.isArray(parsed.anchors) || parsed.anchors.length === 0) return null;
  const anchors: TitrationScene["anchors"] = [];
  for (const anchor of parsed.anchors) {
    if (!isJsonRecord(anchor)) return null;
    const label = text(anchor.label);
    if (!label) return null;
    anchors.push({
      label,
      ph: text(anchor.ph) ?? undefined,
      volume: text(anchor.volume) ?? undefined,
      detail: text(anchor.detail) ?? undefined,
      value: text(anchor.value) ?? undefined,
    });
  }
  return { kind: "titration", title, region, anchors };
}

function parseEquilibrium(parsed: Record<string, unknown>, title: string): EquilibriumScene | null {
  if (!Array.isArray(parsed.rows) || parsed.rows.length === 0) return null;
  const rows: EquilibriumScene["rows"] = [];
  for (const row of parsed.rows) {
    if (!isJsonRecord(row)) return null;
    const species = text(row.species);
    const initial = text(row.initial);
    const change = text(row.change);
    const equilibrium = typeof row.equilibrium === "string" ? row.equilibrium : null;
    if (!species || !initial || !change || equilibrium === null) return null;
    rows.push({ species, initial, change, equilibrium });
  }
  return { kind: "equilibrium", title, rows };
}

function parseCell(parsed: Record<string, unknown>, title: string): CellScene | null {
  const anode = text(parsed.anode);
  const cathode = text(parsed.cathode);
  const potential = text(parsed.potential);
  const electrons = text(parsed.electrons);
  if (!anode || !cathode || !potential || !electrons) return null;
  return { kind: "cell", title, anode, cathode, potential, electrons };
}
