/**
 * Classify a fenced block for the crash-fallback renderer.
 *
 * When the rich markdown renderer throws, `FallbackMarkdown` renders a
 * best-effort view. Callouts stay as labeled prose. Geometry/graph keep their
 * SVG renderers. Server transport (sources/answer), model places, and heavy visuals
 * degrade to a short human summary — never raw JSON or SDF dumps.
 */
import { splitAnswerNotation } from "@/lib/answerNotation";
import { parseGraphSpec } from "@/lib/math/graphSpec";
import { parseGeometrySpec } from "@/lib/math/geometryBlock";
import { fenceIdForLang, fallbackKindForLang } from "@/lib/fenceRegistry";
import { parseJsonRecord } from "@/lib/jsonFence";
import { parseCalloutKind, type CalloutKind } from "@/lib/richBlocks";
import { parseSearchSourcesJson } from "@/lib/searchSources";
import { parsePlacesJson } from "@/lib/places/placesList";

const VISUAL_SNIPPET_MAX = 80;

type FallbackNamedItem = { title: string; url?: string };

type FallbackFence =
  | { kind: "callout"; calloutKind: CalloutKind; body: string }
  | { kind: "geometry"; body: string }
  | { kind: "graph"; body: string }
  | { kind: "answer"; body: string }
  | { kind: "sources"; items: FallbackNamedItem[] }
  | { kind: "places"; items: FallbackNamedItem[] }
  | { kind: "visual"; labelLang: string; snippet: string }
  | { kind: "code"; lang: string; code: string };

function firstNonEmptyLine(text: string): string {
  const lines = text.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed) return trimmed;
  }
  return "";
}

function lastNonEmptyLine(text: string): string {
  const lines = text.split("\n");
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const trimmed = lines[i]?.trim() ?? "";
    if (trimmed) return trimmed;
  }
  return "";
}

function clipSnippet(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= VISUAL_SNIPPET_MAX) return compact;
  return `${compact.slice(0, VISUAL_SNIPPET_MAX).trim()}…`;
}

function visualSnippet(lang: string, body: string): string {
  const id = fenceIdForLang(lang);
  if (id === "molecule") {
    const trimmed = body.trim();
    // Never dump the SDF JSON.
    const row = trimmed.startsWith("{") ? parseJsonRecord(trimmed) : null;
    if (row) {
      if (typeof row.caption === "string" && row.caption.trim()) {
        return clipSnippet(row.caption.trim());
      }
      if (typeof row.smiles === "string" && row.smiles.trim()) {
        return clipSnippet(row.smiles.trim());
      }
    }
    return "";
  }
  if (id === "molecule3d") {
    const last = lastNonEmptyLine(body);
    if (last && last.length <= VISUAL_SNIPPET_MAX && !last.startsWith("{")) {
      return last;
    }
    return "";
  }
  const trimmed = body.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    // A title when the spec has one; never dump the spec.
    const title = parseJsonRecord(trimmed)?.title;
    if (typeof title === "string" && title.trim()) return clipSnippet(title);
    return "";
  }
  return clipSnippet(firstNonEmptyLine(body));
}

export function classifyFallbackFence(
  lang: string | undefined,
  content: string,
): FallbackFence {
  const l = (lang || "").trim().toLowerCase();
  const body = content.replace(/\n$/, "").trim();
  switch (fallbackKindForLang(l)) {
    case "callout":
      return { kind: "callout", calloutKind: parseCalloutKind(l), body };
    case "geometry":
      return { kind: "geometry", body };
    case "graph":
      return { kind: "graph", body };
    case "answer":
      return { kind: "answer", body: splitAnswerNotation(body).body };
    case "sources": {
      const items = parseSearchSourcesJson(body).map((row) => {
        const item: FallbackNamedItem = { title: row.title || row.url };
        if (row.url) item.url = row.url;
        return item;
      });
      return { kind: "sources", items };
    }
    case "places": {
      const items = parsePlacesJson(body).map((row) => {
        const item: FallbackNamedItem = { title: row.name };
        if (row.url) item.url = row.url;
        return item;
      });
      return { kind: "places", items };
    }
    case "visual":
      return { kind: "visual", labelLang: l, snippet: visualSnippet(l, body) };
  }
  if (l === "json" && parseGeometrySpec(body)) {
    return { kind: "geometry", body };
  }
  if ((l === "json" || l === "") && parseGraphSpec(body)) {
    return { kind: "graph", body };
  }
  return { kind: "code", lang: l, code: body };
}
