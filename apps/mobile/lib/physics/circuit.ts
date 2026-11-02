/**
 * Parsing and layout for the circuit diagram (`simulation` fence, type `circuit`).
 *
 * The server says what is connected to what — a source driving one network of
 * parts in series and in parallel — and what the solver found for each part.
 * Nothing here computes a current or a voltage: this file only decides where
 * each symbol, wire and label goes, as a pure function the `lib` tests can
 * assert directly.
 *
 * The schematic is the classic rectangular loop: the source on the left edge,
 * the load network along the top wire, and the return wire along the bottom.
 * Series groups run left to right; a parallel group stacks its branches
 * between two vertical rails, with the first branch on the main wire so the
 * top of the loop stays straight.
 */

import { guard, optionalText, refuse, requireRecord } from "@/lib/fenceValidate";

export type CircuitPartKind =
  | "resistor"
  | "bulb"
  | "capacitor"
  | "inductor"
  | "ammeter"
  | "voltmeter"
  | "switch";

export type CircuitRole = "given" | "result";

type CircuitPartNode = {
  kind: "part";
  part: CircuitPartKind;
  label?: string;
  detail?: string;
  role: CircuitRole;
};

type CircuitGroupNode = {
  kind: "series" | "parallel";
  children: CircuitNode[];
  label?: string;
  detail?: string;
  role: CircuitRole;
};

type CircuitNode = CircuitPartNode | CircuitGroupNode;

export type CircuitSourceKind = "battery" | "ac";

export type CircuitSpec = {
  source: { kind: CircuitSourceKind; label?: string };
  load: CircuitNode;
  /** The source current, drawn as an arrow on the wire beside the source. */
  current?: string;
};

const CIRCUIT_PARTS: readonly CircuitPartKind[] = [
  "resistor",
  "bulb",
  "capacitor",
  "inductor",
  "ammeter",
  "voltmeter",
  "switch",
];
export const MAX_CIRCUIT_PARTS = 10;
const MAX_CIRCUIT_DEPTH = 3;
const SERIES_LIMITS = [2, 6] as const;
const PARALLEL_LIMITS = [2, 4] as const;
const MAX_LABEL = 24;

function role(value: unknown): CircuitRole {
  if (value === undefined || value === null || value === "given") return "given";
  if (value === "result") return "result";
  return refuse();
}

function parseNode(raw: unknown, level: number, count: { parts: number }): CircuitNode {
  const row = requireRecord(raw);
  const has = (key: string) => row[key] !== undefined && row[key] !== null;
  const kinds = [has("part"), has("series"), has("parallel")].filter(Boolean).length;
  if (kinds !== 1) refuse();
  const label = optionalText(row.label, MAX_LABEL);
  const detail = optionalText(row.detail, MAX_LABEL);
  const nodeRole = role(row.role);

  if (has("part")) {
    if (!CIRCUIT_PARTS.includes(row.part as CircuitPartKind)) refuse();
    count.parts += 1;
    if (count.parts > MAX_CIRCUIT_PARTS) refuse();
    return { kind: "part", part: row.part as CircuitPartKind, label, detail, role: nodeRole };
  }

  // A group one level deeper than the server allows is refused on the way
  // down, so a pathological fence never recurses far.
  if (level > MAX_CIRCUIT_DEPTH) refuse();
  const kind = has("series") ? "series" : "parallel";
  const list = row[kind];
  const [min, max] = kind === "series" ? SERIES_LIMITS : PARALLEL_LIMITS;
  if (!Array.isArray(list) || list.length < min || list.length > max) refuse();
  const children = list.map((child) => parseNode(child, level + 1, count));
  return { kind, children, label, detail, role: nodeRole };
}

/**
 * Read the `circuit` object of a fence, or null when it is malformed.
 *
 * As strict as the server model: an unknown part, a group with one member, a
 * network deeper than three groups or with more than ten parts is refused
 * whole rather than drawn in part.
 */
export function parseCircuitSpec(raw: unknown): CircuitSpec | null {
  return guard(() => {
    const row = requireRecord(raw);
    const sourceRow = requireRecord(row.source);
    const kind = sourceRow.kind ?? "battery";
    if (kind !== "battery" && kind !== "ac") refuse();
    const load = parseNode(row.load, 1, { parts: 0 });
    return {
      source: { kind, label: optionalText(sourceRow.label, MAX_LABEL) },
      load,
      current: optionalText(row.current, MAX_LABEL),
    };
  });
}

export function circuitPartCount(node: CircuitNode): number {
  return node.kind === "part"
    ? 1
    : node.children.reduce((sum, child) => sum + circuitPartCount(child), 0);
}

export function circuitDepth(node: CircuitNode): number {
  return node.kind === "part" ? 0 : 1 + Math.max(...node.children.map(circuitDepth));
}

// --- layout ---------------------------------------------------------------------

/** Above a 12 pt label's baseline: cap height plus a little for accents. */
export const TEXT_ASCENT = 9;
/** Below the baseline: subscripts (R₁) and descenders. */
export const TEXT_DESCENT = 3;
const TEXT_HEIGHT = TEXT_ASCENT + TEXT_DESCENT;
/** Every symbol fits within this distance of its wire, so a row's labels align. */
const SYMBOL_HALF_HEIGHT = 9;
const LABEL_GAP = 4;
/** Room between neighbouring labels. */
const LABEL_PAD = 8;
/** Shortest slot a part takes along the wire, symbol plus a lead each side. */
const PART_MIN_WIDTH = 40;
const SERIES_GAP = 10;
const RAIL_LEAD = 10;
const BRANCH_GAP = 8;
const BRACKET_GAP = 6;
export const BRACKET_TICK = 4;
const BRACKET_TEXT_GAP = 3;
/** Wire from a corner of the loop to the network. */
const CORNER_LEAD = 22;
/** Shortest left edge: room for the source and the current arrow above it. */
const MIN_LOOP_HEIGHT = 72;
const BOTTOM_GAP = 12;
const EDGE = 6;
/** Half the battery's long plate, which pokes out either side of the wire. */
export const SOURCE_HALF_WIDTH = 12;
const SOURCE_TEXT_GAP = 6;
/** Half the source's extent along its wire (the AC circle's radius). */
export const SOURCE_HALF_SPAN = 10;
const CURRENT_ARROW = 12;

/** How far each symbol reaches along its wire from its centre; the leads stop there. */
export const PART_HALF_SPAN: Record<CircuitPartKind, number> = {
  resistor: 14,
  bulb: 9,
  capacitor: 3,
  inductor: 14,
  ammeter: 9,
  voltmeter: 9,
  switch: 12,
};

/** A label: `x` is its left edge and `y` its baseline, in layout units. */
export type TextMark = { text: string; x: number; y: number; width: number };
type WireSegment = { x1: number; y1: number; x2: number; y2: number };
type PartMark = {
  part: CircuitPartKind;
  cx: number;
  cy: number;
  role: CircuitRole;
  label?: TextMark;
  detail?: TextMark;
};
/** A light bracket over a group, with its combined value above it. */
type GroupMark = { x1: number; x2: number; y: number; role: CircuitRole; text: TextMark };
type SourceMark = { kind: CircuitSourceKind; cx: number; cy: number; label?: TextMark };
/** An upward arrow on the left wire: current leaving the source's top terminal. */
type CurrentMark = { x: number; tailY: number; tipY: number; label: TextMark };

export type CircuitLayout = {
  /** Size of the drawing before it is scaled to fit. */
  naturalWidth: number;
  naturalHeight: number;
  /** One scale for the whole drawing, text included; never above 1. */
  scale: number;
  /** Horizontal offset that centres the scaled drawing in the canvas. */
  offsetX: number;
  /** The canvas: the full figure width, and the scaled drawing's height. */
  width: number;
  height: number;
  wires: WireSegment[];
  junctions: { x: number; y: number }[];
  parts: PartMark[];
  groups: GroupMark[];
  source: SourceMark;
  current: CurrentMark | null;
};

type MeasureText = (text: string) => number;

type Measured = {
  node: CircuitNode;
  /** Slot width along the wire. */
  width: number;
  /** Width of what the group bracket spans (the members, not the padding). */
  contentWidth: number;
  /** Extent above and below the node's wire, labels and brackets included. */
  ascent: number;
  descent: number;
  /** The ascent of the members, under the bracket. */
  contentAscent: number;
  children: Measured[];
  /** Parallel only: each branch's wire, measured down from the first. */
  offsets: number[];
  groupText?: string;
  groupTextWidth: number;
};

function groupText(node: CircuitNode): string | undefined {
  const parts = [node.label, node.detail].filter((text): text is string => Boolean(text));
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

function measureNode(node: CircuitNode, measure: MeasureText): Measured {
  if (node.kind === "part") {
    const labelWidth = node.label ? measure(node.label) : 0;
    const detailWidth = node.detail ? measure(node.detail) : 0;
    const width = Math.max(PART_MIN_WIDTH, labelWidth + LABEL_PAD, detailWidth + LABEL_PAD);
    const ascent = SYMBOL_HALF_HEIGHT + (node.label ? LABEL_GAP + TEXT_HEIGHT : 2);
    return {
      node,
      width,
      contentWidth: width,
      ascent,
      descent: SYMBOL_HALF_HEIGHT + (node.detail ? LABEL_GAP + TEXT_HEIGHT : 2),
      contentAscent: ascent,
      children: [],
      offsets: [],
      groupTextWidth: 0,
    };
  }

  const children = node.children.map((child) => measureNode(child, measure));
  let contentWidth: number;
  let contentAscent: number;
  let descent: number;
  const offsets: number[] = [];
  if (node.kind === "series") {
    contentWidth =
      children.reduce((sum, child) => sum + child.width, 0) + SERIES_GAP * (children.length - 1);
    contentAscent = Math.max(...children.map((child) => child.ascent));
    descent = Math.max(...children.map((child) => child.descent));
  } else {
    contentWidth = Math.max(...children.map((child) => child.width)) + RAIL_LEAD * 2;
    contentAscent = children[0].ascent;
    let y = 0;
    children.forEach((child, index) => {
      if (index > 0) y += children[index - 1].descent + BRANCH_GAP + child.ascent;
      offsets.push(y);
    });
    descent = y + children[children.length - 1].descent;
  }
  const text = groupText(node);
  const textWidth = text ? measure(text) : 0;
  return {
    node,
    width: Math.max(contentWidth, text ? textWidth + LABEL_PAD : 0),
    contentWidth,
    ascent: contentAscent + (text ? BRACKET_GAP + BRACKET_TEXT_GAP + TEXT_HEIGHT : 0),
    descent,
    contentAscent,
    children,
    offsets,
    groupText: text,
    groupTextWidth: textWidth,
  };
}

type Out = Pick<CircuitLayout, "wires" | "junctions" | "parts" | "groups">;

function centred(text: string, width: number, cx: number, baseline: number): TextMark {
  return { text, x: cx - width / 2, y: baseline, width };
}

function wire(out: Out, x1: number, y1: number, x2: number, y2: number) {
  if (x1 !== x2 || y1 !== y2) out.wires.push({ x1, y1, x2, y2 });
}

/** Lay `m` out with its slot starting at `x` and its wire at `y`. */
function placeNode(m: Measured, x: number, y: number, out: Out, measure: MeasureText) {
  const node = m.node;
  if (node.kind === "part") {
    const cx = x + m.width / 2;
    const half = PART_HALF_SPAN[node.part];
    wire(out, x, y, cx - half, y);
    wire(out, cx + half, y, x + m.width, y);
    out.parts.push({
      part: node.part,
      cx,
      cy: y,
      role: node.role,
      label: node.label
        ? centred(node.label, measure(node.label), cx, y - SYMBOL_HALF_HEIGHT - LABEL_GAP - TEXT_DESCENT)
        : undefined,
      detail: node.detail
        ? centred(node.detail, measure(node.detail), cx, y + SYMBOL_HALF_HEIGHT + LABEL_GAP + TEXT_ASCENT)
        : undefined,
    });
    return;
  }

  // A label wider than the members pads the group with wire on both sides.
  const left = x + (m.width - m.contentWidth) / 2;
  const right = left + m.contentWidth;
  wire(out, x, y, left, y);
  wire(out, right, y, x + m.width, y);

  if (node.kind === "series") {
    let cursor = left;
    m.children.forEach((child, index) => {
      if (index > 0) {
        wire(out, cursor, y, cursor + SERIES_GAP, y);
        cursor += SERIES_GAP;
      }
      placeNode(child, cursor, y, out, measure);
      cursor += child.width;
    });
  } else {
    const inner = m.contentWidth - RAIL_LEAD * 2;
    const last = m.offsets[m.offsets.length - 1];
    wire(out, left, y, left, y + last);
    wire(out, right, y, right, y + last);
    m.children.forEach((child, index) => {
      const branchY = y + m.offsets[index];
      const start = left + RAIL_LEAD + (inner - child.width) / 2;
      wire(out, left, branchY, start, branchY);
      placeNode(child, start, branchY, out, measure);
      wire(out, start + child.width, branchY, right, branchY);
      // A dot where a branch tees off a rail; the last branch turns a corner.
      if (index < m.children.length - 1) {
        out.junctions.push({ x: left, y: branchY }, { x: right, y: branchY });
      }
    });
  }

  if (m.groupText) {
    const bracketY = y - m.contentAscent - BRACKET_GAP;
    out.groups.push({
      x1: left,
      x2: right,
      y: bracketY,
      role: node.role,
      text: centred(m.groupText, m.groupTextWidth, (left + right) / 2, bracketY - BRACKET_TEXT_GAP - TEXT_DESCENT),
    });
  }
}

/**
 * Lay a circuit out for a canvas `width` wide.
 *
 * `measure` gives a label's width as the renderer draws it (12 pt). The renderer and
 * the list placeholder pass the same estimate, so the height a chat cell
 * reserves is the height the diagram takes.
 *
 * The drawing is laid out at its natural size and then scaled as a whole —
 * text included — when it is wider than the canvas, so it never overflows
 * and the labels keep their places relative to their symbols.
 */
export function layoutCircuit(spec: CircuitSpec, width: number, measure: MeasureText): CircuitLayout {
  const root = measureNode(spec.load, measure);
  const out: Out = { wires: [], junctions: [], parts: [], groups: [] };

  const sourceLabelWidth = spec.source.label ? measure(spec.source.label) : 0;
  const currentLabelWidth = spec.current ? measure(spec.current) : 0;
  const gutter = Math.max(sourceLabelWidth, currentLabelWidth);
  const leftX = EDGE + (gutter > 0 ? gutter + SOURCE_TEXT_GAP : 0) + SOURCE_HALF_WIDTH;
  const topY = EDGE + Math.max(root.ascent, TEXT_ASCENT);
  const networkX = leftX + CORNER_LEAD;
  const rightX = networkX + root.width + CORNER_LEAD;
  const bottomY = topY + Math.max(MIN_LOOP_HEIGHT, root.descent + BOTTOM_GAP);

  placeNode(root, networkX, topY, out, measure);
  // The loop: top-left corner to the network, network to the right edge,
  // down, and back along the bottom. The left edge is split by the source.
  const sourceY = (topY + bottomY) / 2;
  wire(out, leftX, topY, networkX, topY);
  wire(out, networkX + root.width, topY, rightX, topY);
  wire(out, rightX, topY, rightX, bottomY);
  wire(out, rightX, bottomY, leftX, bottomY);
  wire(out, leftX, topY, leftX, sourceY - SOURCE_HALF_SPAN);
  wire(out, leftX, sourceY + SOURCE_HALF_SPAN, leftX, bottomY);

  // Labels sit in the gutter, right-aligned against the source.
  const gutterRight = leftX - SOURCE_HALF_WIDTH - SOURCE_TEXT_GAP;
  const middle = (TEXT_ASCENT - TEXT_DESCENT) / 2;
  const source: SourceMark = {
    kind: spec.source.kind,
    cx: leftX,
    cy: sourceY,
    label: spec.source.label
      ? { text: spec.source.label, x: gutterRight - sourceLabelWidth, y: sourceY + middle, width: sourceLabelWidth }
      : undefined,
  };
  let current: CurrentMark | null = null;
  if (spec.current) {
    const arrowY = (topY + sourceY - SOURCE_HALF_SPAN) / 2;
    current = {
      x: leftX,
      tailY: arrowY + CURRENT_ARROW / 2,
      tipY: arrowY - CURRENT_ARROW / 2,
      label: {
        text: spec.current,
        x: gutterRight - currentLabelWidth,
        y: arrowY + middle,
        width: currentLabelWidth,
      },
    };
  }

  const naturalWidth = rightX + EDGE;
  const naturalHeight = bottomY + EDGE;
  const scale = Math.min(1, width / naturalWidth);
  return {
    naturalWidth,
    naturalHeight,
    scale,
    offsetX: (width - naturalWidth * scale) / 2,
    width,
    height: Math.ceil(naturalHeight * scale),
    ...out,
    source,
    current,
  };
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

function describeNode(node: CircuitNode, t: Translate, nested: boolean): string {
  if (node.kind === "part") {
    const name = t(`rich.diagram_part_${node.part}`);
    const label = node.label ? ` ${node.label}` : "";
    const detail = node.detail ? ` (${node.detail})` : "";
    return `${name}${label}${detail}`;
  }
  const list = node.children.map((child) => describeNode(child, t, true)).join(", ");
  const text = groupText(node);
  const group = `${t(`rich.diagram_a11y_${node.kind}`, { list })}${text ? `: ${text}` : ""}`;
  return nested ? `(${group})` : group;
}

/** What a screen reader says when the fence has no `alt`. */
export function describeCircuit(spec: CircuitSpec, t: Translate): string {
  const source = `${t(`rich.diagram_source_${spec.source.kind}`)}${
    spec.source.label ? ` ${spec.source.label}` : ""
  }`;
  const sentences = [t("rich.diagram_a11y_circuit", { source, load: describeNode(spec.load, t, false) })];
  if (spec.current) sentences.push(t("rich.diagram_a11y_current", { value: spec.current }));
  return sentences.join(". ") + ".";
}
