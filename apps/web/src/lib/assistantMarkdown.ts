/** Prepare assistant markdown for the web slice: strip transport fences,
 * turn remaining rich fences into a short human label, never dump JSON. */

import type { SearchSource } from "@/api/types";
import { visibleAnswerBody } from "./answerNotation.ts";
import { chemSceneMarkdown } from "./chemScene.ts";
import { stripDraftFormSlots } from "./draftSanitize.ts";
import { normalizeMarkdownTables, splitSwallowedCodeFenceTables } from "./markdownTables.ts";

export type { SearchSource };

type Fence = {
  lang: string;
  body: string;
  start: number;
  end: number;
};

const VISUAL_LABELS: Record<string, string> = {
  chart: "Chart",
  vega: "Chart",
  "vega-lite": "Chart",
  plot: "Chart",
  mermaid: "Diagram",
  geometry: "Diagram",
  graph: "Graph",
  smiles: "Chemical structure",
  chemistry: "Chemical structure",
  molecule: "Chemical structure",
  molecule3d: "Chemical structure",
  mol3d: "Chemical structure",
  "3dmol": "Chemical structure",
  chem_scene: "Chemistry diagram",
  arithmetic: "Calculation",
  simulation: "Simulation",
};

const CHEM_VISUAL_LANGS = new Set(["smiles", "chemistry"]);
const MOL3D_LANGS = new Set(["molecule3d", "mol3d", "3dmol"]);

const CALLOUT_LANGS = new Set([
  "tip",
  "note",
  "warning",
  "info",
  "important",
  "callout",
  "callout-tip",
  "callout-note",
  "callout-warning",
  "callout-info",
  "callout-important",
]);

const ANSWER_LANGS = new Set(["answer", "result", "final"]);

const DRAFT_LANGS = new Set(["email", "sms", "social"]);

function fenceLang(info: string): string {
  const stripped = info.trim();
  if (!stripped) return "";
  const space = stripped.indexOf(" ");
  const token = space < 0 ? stripped : stripped.slice(0, space);
  return token.toLowerCase();
}

/** Walk ``` fences with linear `indexOf` (no nested regex). */
function iterFences(text: string): Fence[] {
  const fences: Fence[] = [];
  let index = 0;
  const length = text.length;
  while (true) {
    const start = text.indexOf("```", index);
    if (start < 0) break;
    const langStart = start + 3;
    const newline = text.indexOf("\n", langStart);
    if (newline < 0) {
      fences.push({
        lang: fenceLang(text.slice(langStart)),
        body: "",
        start,
        end: length,
      });
      break;
    }
    const lang = fenceLang(text.slice(langStart, newline));
    const close = text.indexOf("```", newline + 1);
    if (close < 0) {
      fences.push({
        lang,
        body: text.slice(newline + 1),
        start,
        end: length,
      });
      break;
    }
    fences.push({
      lang,
      body: text.slice(newline + 1, close),
      start,
      end: close + 3,
    });
    index = close + 3;
  }
  return fences;
}

function firstNonEmptyLine(text: string): string {
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed) return trimmed;
  }
  return "";
}

function clipSnippet(text: string, max = 80): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= max) return compact;
  return `${compact.slice(0, max).trimEnd()}…`;
}

function jsonTitle(body: string): string {
  const trimmed = body.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return "";
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const title = (parsed as { title?: unknown }).title;
      if (typeof title === "string" && title.trim()) return clipSnippet(title.trim());
    }
  } catch {
    // Never dump the spec.
  }
  return "";
}

export function parseSearchSourcesJson(raw: string): SearchSource[] {
  let text = raw.trim();
  if (text.endsWith("```")) {
    const idx = text.lastIndexOf("```");
    text = text.slice(0, idx).trim();
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const row = item as Record<string, unknown>;
      const title = String(row.title ?? "").trim();
      const url = String(row.url ?? "").trim();
      if (!title && !url) return [];
      const snippet = String(row.snippet ?? "").trim();
      const source: SearchSource = { title: title || url, url };
      if (snippet) source.snippet = snippet;
      return [source];
    });
  } catch {
    return [];
  }
}

type PlaceItem = { name: string; url?: string };

function parsePlacesJson(raw: string): PlaceItem[] {
  try {
    const parsed: unknown = JSON.parse(raw.trim());
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const row = item as Record<string, unknown>;
      const name = String(row.name ?? "").trim();
      if (!name) return [];
      const url = String(row.url ?? "").trim();
      const place: PlaceItem = { name };
      if (url) place.url = url;
      return [place];
    });
  } catch {
    return [];
  }
}

function looksLikeSourcesArray(body: string): boolean {
  return parseSearchSourcesJson(body).length > 0;
}

function isSourcesFence(fence: Fence): boolean {
  return fence.lang === "sources" || (fence.lang === "" && looksLikeSourcesArray(fence.body));
}

export function parseSearchSourcesFromMarkdown(content: string): SearchSource[] {
  const fromFences = iterFences(content).flatMap((fence) =>
    isSourcesFence(fence) ? parseSearchSourcesJson(fence.body) : [],
  );
  if (fromFences.length > 0) return fromFences;
  return [];
}

export function stripSearchSourcesFromContent(content: string): string {
  const fences = iterFences(content).filter(isSourcesFence);
  if (fences.length === 0) return content.trimEnd();
  const parts: string[] = [];
  let cursor = 0;
  for (const fence of fences) {
    parts.push(content.slice(cursor, fence.start));
    cursor = fence.end;
  }
  parts.push(content.slice(cursor));
  return parts.join("").replace(/\n{3,}/g, "\n\n").trimEnd();
}

function markdownLinkList(items: { title: string; url?: string }[]): string {
  if (items.length === 0) return "";
  return items
    .map((item) =>
      item.url ? `- [${item.title}](${item.url})` : `- ${item.title}`,
    )
    .join("\n");
}

function visualFallback(lang: string, body: string): string {
  if (lang === "chem_scene") return chemSceneMarkdown(body);
  const label = VISUAL_LABELS[lang] ?? "Diagram";
  const title = jsonTitle(body) || (body.trim().startsWith("{") ? "" : clipSnippet(firstNonEmptyLine(body)));
  return title ? `*${label}: ${title}*` : `*${label}*`;
}

function draftFallback(lang: string, body: string): string {
  const sanitized = stripDraftFormSlots(body);
  if (!sanitized) return "";
  const label = lang === "email" ? "Email" : lang === "sms" ? "Text message" : "Post";
  const quoted = sanitized.replace(/\n/g, "\n> ");
  return `> **${label}**\n> ${quoted}`;
}

function fallbackForFence(fence: Fence): string {
  const lang = fence.lang;
  if (isSourcesFence(fence)) return "";
  if (lang === "places" || (lang === "json" && parsePlacesJson(fence.body).length > 0)) {
    return markdownLinkList(
      parsePlacesJson(fence.body).map((row) => ({
        title: row.name,
        url: row.url,
      })),
    );
  }
  if (ANSWER_LANGS.has(lang)) {
    return visibleAnswerBody(fence.body);
  }
  if (lang in VISUAL_LABELS) {
    return visualFallback(lang, fence.body);
  }
  if (CALLOUT_LANGS.has(lang)) {
    const body = fence.body.trim();
    return body ? `> ${body.replace(/\n/g, "\n> ")}` : "";
  }
  if (DRAFT_LANGS.has(lang)) {
    return draftFallback(lang, fence.body);
  }
  // Unknown / code / math: keep the original fence so marked can render a <pre>.
  return "";
}

function shouldReplaceFence(fence: Fence): boolean {
  if (isSourcesFence(fence)) return true;
  if (fence.lang === "places") return true;
  if (fence.lang === "json" && parsePlacesJson(fence.body).length > 0) return true;
  if (ANSWER_LANGS.has(fence.lang)) return true;
  if (fence.lang in VISUAL_LABELS) return true;
  if (CALLOUT_LANGS.has(fence.lang)) return true;
  if (DRAFT_LANGS.has(fence.lang)) return true;
  return false;
}

function isPairedMolecule3d(prev: Fence | null, fence: Fence, markdown: string): boolean {
  if (!prev || !MOL3D_LANGS.has(fence.lang) || !CHEM_VISUAL_LANGS.has(prev.lang)) {
    return false;
  }
  return markdown.slice(prev.end, fence.start).trim() === "";
}

/** Replace known rich fences with a human summary; leave real code/math alone. */
function replaceRichFences(markdown: string): string {
  const fences = iterFences(markdown);
  if (fences.length === 0) return markdown;
  const parts: string[] = [];
  let cursor = 0;
  let prev: Fence | null = null;
  let replaced = false;
  let sawChemCard = false;
  for (const fence of fences) {
    if (shouldReplaceFence(fence)) {
      parts.push(markdown.slice(cursor, fence.start));
      // Persist still emits smiles + molecule3d. Skip later 3D fences once a
      // chemistry card already produced a label (model often adds a second
      // ```molecule3d under a "3D Structure" heading).
      const skipMol3d =
        MOL3D_LANGS.has(fence.lang) &&
        (sawChemCard || isPairedMolecule3d(prev, fence, markdown));
      parts.push(skipMol3d ? "" : fallbackForFence(fence));
      cursor = fence.end;
      replaced = true;
      if (CHEM_VISUAL_LANGS.has(fence.lang) || fence.lang === "molecule") {
        sawChemCard = true;
      }
    }
    prev = fence;
  }
  if (!replaced) return markdown;
  parts.push(markdown.slice(cursor));
  return parts.join("").replace(/\n{3,}/g, "\n\n");
}

export function prepareAssistantMarkdown(markdown: string): string {
  const withoutUnverified = (markdown ?? "").replace(
    /[ \t]*\*?I couldn't automatically verify this result\.\*?[ \t]*/g,
    "",
  );
  const stripped = stripSearchSourcesFromContent(withoutUnverified);
  const split = splitSwallowedCodeFenceTables(stripped, iterFences(stripped));
  return replaceRichFences(normalizeMarkdownTables(split));
}
