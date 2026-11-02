/**
 * Single source of truth for fence identity and per-fence behaviour flags.
 *
 * Adding or removing a fence type used to mean editing four independently
 * maintained language lists — `STRUCTURED_LANGS` in richBlocks.ts, the
 * code-block exclusions and copy-block list in copyBlock.ts, the pre-dispatch
 * lists in markdownFenceRender.tsx, and the crash-path classifier in
 * fallbackFence.ts. They had already drifted: `sources` and `copy` were known
 * to copyBlock alone, while 18 langs including `chart`, `mermaid` and `steps`
 * were known only to richBlocks.
 *
 * The two sets below are intentionally NOT unified — `structured` (does this
 * enter the rich renderer?) and `neverCodeBlock` (is this excluded from
 * syntax-highlighted code rendering?) genuinely differ, and collapsing them
 * would change what renders. The point is that the difference is now declared
 * per fence and reviewable in one table, instead of being an accident of which
 * list someone remembered to update.
 *
 * Every other per-fence behaviour (copy and read-aloud, lifting out of lists,
 * the open streaming tail, the crash fallback) is a field on the fence's row
 * too, and `FenceId` is read off the table: a new fence is one row here plus
 * its renderer (`components/rich/README.md` has the recipe).
 *
 * `owner` classifies who may emit the fence on new turns:
 * - model: the active prompt may produce this
 * - server: Recall attaches or rewrites this after the stream
 * - legacy: still rendered for history; the prompt must not choose it for layout
 *
 * Do not add FenceId values casually. Prefer Markdown, `>` callouts/quotes, and
 * GFM tables. New layout fences need a prompt contract, a renderer, stream
 * preview, and preprocess — freeze the set unless the user-visible object is
 * truly new.
 *
 * Reminder / settings control fences are parsed outside this registry (see
 * assistantMessageContent.ts), which also strips the retired
 * `calendar_proposal` fence that old saved replies may still carry.
 */

type FenceOwner = "model" | "server" | "legacy";

/**
 * What a fence's body is. It decides what the open streaming tail shows before
 * the fence closes (`classifyOpenFencePreview`):
 * - data: JSON or another machine format the card draws (a quiz, a graph, a
 *   SMILES string, a trace's numbered lines). Never shown raw: the open tail is
 *   a quiet placeholder until the fence closes and the card can draw.
 * - prose: text the card wraps (a drafted email, a callout). It streams as reply text.
 * - latex: typeset by the native math preview.
 */
type FenceBody = "data" | "prose" | "latex";

type FallbackKind =
  | "callout"
  | "geometry"
  | "graph"
  | "answer"
  | "sources"
  | "places"
  | "visual";

/**
 * What a whole-message copy and read-aloud make of the body
 * (`lib/markdown/plain.ts`). Omitted: the body is the text.
 * - drop: transport or control data, neither copied nor spoken.
 * - chart / diagram: spoken as "a chart" / "a diagram", not copied.
 */
type FencePlainText = "drop" | "chart" | "diagram";

/**
 * A body copy and read-aloud read with their own reader (`lib/markdown/plain.ts`) before the
 * `plainText` rule. `worked` with no worked lines falls back to that rule; the rest read as nothing.
 */
export type FencePlainReader = "worked" | "quiz" | "clarify" | "array";

/** A card shown in a shared document (Share, PDF) as a one-line label (`lib/markdown/document.ts`). */
export type FenceDocumentBlock = "chart" | "graph" | "diagram" | "molecule" | "calculator" | "places";

type FenceSpecRow = {
  id: string;
  /** Every language tag that resolves to this fence. */
  langs: readonly string[];
  /** Routed through the rich fence renderer (was `STRUCTURED_LANGS`). */
  structured: boolean;
  /** Never rendered as a syntax-highlighted code block (was copyBlock's list). */
  neverCodeBlock: boolean;
  /** Who may emit this fence on new turns. */
  owner: FenceOwner;
  /** What the body is; a `data` body never streams raw. */
  body: FenceBody;
  /** How the crash-fallback renderer degrades this fence, when not plain code. */
  fallback?: FallbackKind;
  /** How a whole-message copy and read-aloud treat the body. */
  plainText?: FencePlainText;
  /** The reader a whole-message copy and read-aloud draw the body with, first. */
  plainReader?: FencePlainReader;
  /** In a shared document: its copy text, or the label in the card's place (default: plainText's). */
  inDocument?: "copyText" | FenceDocumentBlock;
  /** A ```json or unlabelled fence whose body is this card's JSON draws as this card. */
  bareJson?: boolean;
  /** A drafted message (email, text, post): a body that reads as no draft renders as prose. */
  draft?: boolean;
  /** Display maths or a maths diagram: a code-card fallback of it has no Copy. */
  mathDiagram?: boolean;
  /** Lifted out of a list item so CommonMark reads it as a real fence. */
  liftOutOfLists?: boolean;
};

const FENCE_TABLE = [
  { id: "email", langs: ["email"], structured: true, neverCodeBlock: true, owner: "model", body: "prose", draft: true },
  {
    id: "quote",
    langs: ["quote", "blockquote"],
    structured: true,
    neverCodeBlock: false,
    owner: "legacy", body: "prose",
  },
  {
    id: "comparison",
    langs: ["compare", "comparison", "pros"],
    structured: true,
    neverCodeBlock: false,
    owner: "legacy", body: "data",
  },
  {
    id: "keyvalue",
    langs: ["kv", "keyvalue", "fields"],
    structured: true,
    neverCodeBlock: false,
    owner: "legacy", body: "data",
  },
  {
    // A lesson's trace: numbered step cards, a state line under each.
    id: "steps",
    langs: ["steps", "step"],
    structured: true,
    neverCodeBlock: false,
    owner: "model", body: "data",
  },
  {
    // Practice: a lesson's "Your turn", a quiz, true/false or a flashcard (no
    // options: the back behind Show answer). Checked on the phone, nothing sent.
    id: "quiz",
    langs: ["quiz"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "data",
    plainReader: "quiz",
    inDocument: "copyText",
  },
  {
    // A few questions with choices when the answer depends on the user (docs/clarify.md):
    // Submit sends the picks as their next message.
    id: "clarify",
    langs: ["clarify"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "data",
    plainReader: "clarify",
    inDocument: "copyText",
  },
  {
    // A lesson's list as boxes, each value over its index.
    id: "array",
    langs: ["array"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "data",
    plainReader: "array",
    inDocument: "copyText",
  },
  // `details`, `collapse`, and `summary` are unwrapped to markdown before
  // this table. They are not fence languages.
  //
  // `latex`/`tex` are aliases of `math`. The model is told never to emit
  // those tags, but it drifts; the settled path already retags closed
  // fences. Registering them here makes the *open* streaming tail typeset
  // instead of landing on CodeBlock (lang badge + raw source).
  {
    id: "math",
    langs: ["math", "latex", "tex"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "latex",
    mathDiagram: true,
    liftOutOfLists: true,
  },
  {
    id: "answer",
    langs: ["answer", "result", "final"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "answer",
    liftOutOfLists: true,
  },
  {
    id: "arithmetic",
    langs: ["arithmetic"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "visual",
    plainText: "diagram",
    mathDiagram: true,
    liftOutOfLists: true,
    plainReader: "worked",
    inDocument: "copyText",
  },
  {
    id: "clock",
    langs: ["clock", "time"],
    structured: true,
    neverCodeBlock: true,
    owner: "legacy", body: "data",
  },
  {
    id: "mermaid",
    langs: ["mermaid"],
    structured: true,
    neverCodeBlock: false,
    owner: "model", body: "data",
    fallback: "visual",
    plainText: "diagram",
  },
  {
    id: "chart",
    langs: ["chart", "vega", "vega-lite", "plot"],
    structured: true,
    neverCodeBlock: false,
    owner: "model", body: "data",
    fallback: "visual",
    plainText: "chart",
  },
  {
    id: "geometry",
    langs: ["geometry"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "geometry",
    plainText: "diagram",
    mathDiagram: true,
    liftOutOfLists: true,
    bareJson: true,
  },
  {
    id: "graph",
    langs: ["graph"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "graph",
    plainText: "diagram",
    mathDiagram: true,
    liftOutOfLists: true,
    inDocument: "graph",
    bareJson: true,
  },
  // Server-owned like geometry/graph: the prompt forbids it and
  // validate_math_fences replaces or strikes out anything the model invents.
  {
    id: "simulation",
    langs: ["simulation"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "visual",
    plainText: "diagram",
  },
  // A loan, a card payoff or savings with sliders (docs/money.md). The server writes it
  // after the reply; the reply's own text states the numbers, so copy and speech drop it.
  {
    id: "calculator",
    langs: ["calculator"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    plainText: "drop",
    inDocument: "calculator",
  },
  {
    id: "chem_scene",
    langs: ["chem_scene"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "visual",
    plainText: "diagram",
  },
  {
    id: "chemistry",
    langs: ["smiles", "chemistry"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "data",
    fallback: "visual",
    plainText: "diagram",
    inDocument: "molecule",
  },
  // Display-only: the client preprocessor collapses an adjacent smiles + molecule3d pair into
  // this. Neither the model nor the server writes it — a stored reply holds only the two
  // source fences — so `owner` names the fence that supplies its content.
  {
    id: "molecule",
    langs: ["molecule"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "visual",
    plainText: "diagram",
    inDocument: "molecule",
  },
  {
    id: "molecule3d",
    langs: ["molecule3d", "mol3d", "3dmol"],
    structured: true,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "visual",
    plainText: "diagram",
    inDocument: "molecule",
  },
  {
    id: "places",
    langs: ["places"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "data",
    fallback: "places",
    plainText: "drop",
    inDocument: "places",
  },
  {
    id: "callout",
    langs: ["tip", "note", "warning", "info", "important", "callout"],
    structured: true,
    neverCodeBlock: false,
    owner: "legacy", body: "prose",
    fallback: "callout",
  },
  {
    id: "social",
    langs: [
      "twitter",
      "tweet",
      "x",
      "linkedin",
      "facebook",
      "fb",
      "instagram",
      "insta",
      "ig",
      "tiktok",
      "threads",
      "caption",
      "social",
    ],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "prose",
    draft: true,
  },
  {
    id: "message",
    langs: ["sms", "message", "reply"],
    structured: true,
    neverCodeBlock: true,
    owner: "model", body: "prose",
    draft: true,
  },
  // Not structured: `copy` and `sources` never reach the rich renderer, but
  // must not fall through to a syntax-highlighted code block either. `sources`
  // is attached by the backend (web_search/formatting.py) onto persisted
  // assistant text and the live `done.final_content`; clients strip it and
  // render the `search_sources` field / parsed fence as a chip.
  { id: "copy", langs: ["copy"], structured: false, neverCodeBlock: true, owner: "model", body: "prose" },
  {
    id: "sources",
    langs: ["sources"],
    structured: false,
    neverCodeBlock: true,
    owner: "server", body: "data",
    fallback: "sources",
    plainText: "drop",
  },
] as const satisfies readonly FenceSpecRow[];

export type FenceId = (typeof FENCE_TABLE)[number]["id"];

type FenceSpec = FenceSpecRow & { id: FenceId };

export const FENCES: readonly FenceSpec[] = FENCE_TABLE;

const BY_LANG = new Map<string, FenceSpec>();
const BY_ID = new Map<FenceId, FenceSpec>();
for (const spec of FENCES) {
  BY_ID.set(spec.id, spec);
  for (const lang of spec.langs) BY_LANG.set(lang, spec);
}

function normalize(lang: string): string {
  return lang.trim().toLowerCase();
}

/** Resolve a fence language tag (including `callout-*`) to its spec. */
export function fenceSpecForLang(lang: string): FenceSpec | null {
  const l = normalize(lang);
  if (l.startsWith("callout-")) return BY_LANG.get("callout") ?? null;
  return BY_LANG.get(l) ?? null;
}

export function fenceIdForLang(lang: string): FenceId | null {
  return fenceSpecForLang(lang)?.id ?? null;
}

/** Routed through the rich fence renderer. */
export function isStructuredFenceLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.structured ?? false;
}

/** Excluded from syntax-highlighted code rendering. */
export function isNeverCodeBlockLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.neverCodeBlock ?? false;
}

/** How the crash-fallback renderer should degrade this fence, if specially. */
export function fallbackKindForLang(lang: string): FallbackKind | null {
  return fenceSpecForLang(lang)?.fallback ?? null;
}

/** Explicit ```math / ```latex / ```tex — never reinterpret as an answer pill. */
export function isMathFenceLang(lang: string): boolean {
  return fenceIdForLang(lang) === "math";
}

/** Display math or a diagram fence — not a syntax-highlighted code card. */
export function isMathDiagramLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.mathDiagram ?? false;
}

/** Read aloud as "a chart"; a whole-message copy leaves it out. */
export function isChartFenceLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.plainText === "chart";
}

/** Geometry / mermaid / chemistry visuals — not charts (those speak as "a chart"). */
export function isVisualDiagramFenceLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.plainText === "diagram";
}

/** What a shared document shows for this fence: its copy text, a card label, or neither. */
export function documentFormForLang(lang: string): "copyText" | FenceDocumentBlock | null {
  const spec = fenceSpecForLang(lang);
  if (spec?.inDocument) return spec.inDocument;
  if (spec?.plainText === "chart") return "chart";
  if (spec?.plainText === "diagram") return "diagram";
  return null;
}

/** A ```json or unlabelled fence whose body is this card's JSON draws as this card. */
export function drawsBareJson(id: FenceId): boolean {
  return BY_ID.get(id)?.bareJson ?? false;
}

/** A card drawn from JSON or another machine format: its open fence never streams raw. */
export function isDataBodyFenceId(id: FenceId): boolean {
  return BY_ID.get(id)?.body === "data";
}

/**
 * Prompt-control fences parsed outside this registry (assistantMessageContent.ts).
 * `calendar_proposal` is retired (Google Calendar was removed); old saved
 * replies may still carry it.
 */
const CONTROL_LANGS: ReadonlySet<string> = new Set([
  "reminder",
  "calendar_proposal",
  "settings_proposal",
  "reminder_proposal",
  "todo_link",
  "photo",
]);

/** Prompt-control JSON plus registry transport fences — never copy or speak. */
export function isControlFenceLang(lang: string): boolean {
  if (fenceSpecForLang(lang)?.plainText === "drop") return true;
  return CONTROL_LANGS.has(normalize(lang));
}

/** Lift these out of list items so CommonMark treats them as real fences. */
export function shouldLiftFenceOutOfList(lang: string): boolean {
  return fenceSpecForLang(lang)?.liftOutOfLists ?? false;
}
