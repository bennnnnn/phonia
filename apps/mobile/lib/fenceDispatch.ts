/**
 * Single fence decision for settled render and the open streaming tail.
 *
 * Priority (do not reorder without a table-driven test):
 *   1. Explicit registered structured tag → that fence (never reinterpret)
 *   2. Explicit programming language → code (never a math-answer heuristic)
 *   3. ```json drift → geometry/graph only when the body is that schema
 *   4. Soft langs (untagged / copy / text / plain) → content heuristics
 */

import { shouldUseHtmlPreview } from "@/lib/codeHighlight";
import {
  isExplicitCodeLang,
  isStructuredDraftLang,
  looksLikeMathAnswer,
  looksLikeExplicitDraftContent,
  shouldRenderAsCodeBlock,
  shouldRenderAsCopyBlock,
} from "@/lib/copyBlock";
import {
  type FenceId,
  drawsBareJson,
  fenceIdForLang,
  fenceSpecForLang,
  isDataBodyFenceId,
  isMathDiagramLang,
} from "@/lib/fenceRegistry";
import {
  isMathFenceInterruptLine,
  looksLikeLatexFence,
  looksLikeMathFenceBody,
} from "@/lib/math/fenceRetag";
import { detectJsonRichFenceKind } from "@/lib/richBlocks";
import {
  isClockFenceBody,
  isDigitalTimeOnly,
  isIanaTimezoneOnly,
} from "@/lib/timeQuestion";

export type FenceRenderKind =
  | "hide"
  | "html"
  | "rich"
  | "answer"
  | "math"
  | "clock"
  | "code"
  | "copy"
  | "prose";

type FenceDecision = {
  kind: FenceRenderKind;
  id?: FenceId;
  lang: string;
};

function isFakeImageGenFence(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  return l === "image" || l === "img" || l === "image-gen" || l === "imagen";
}

function looksLikeMisparsedMarkdownWalkthrough(content: string): boolean {
  if (content.includes("```math") || content.includes("```latex") || content.includes("```tex")) {
    return true;
  }
  return content.split("\n").some((line) => isMathFenceInterruptLine(line));
}

/** Untagged / copy / prose tags — the only place content heuristics may run. */
export function allowsContentHeuristic(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  return !l || l === "copy" || l === "text" || l === "plain" || l === "clike";
}

export function classifyFence(lang: string, content: string): FenceDecision {
  const l = lang.trim().toLowerCase();

  if (isFakeImageGenFence(l)) return { kind: "hide", lang: l };
  // The server swaps a reply's ```photo request for a real photo when it ends.
  if (l === "photo") return { kind: "hide", lang: l };
  if (shouldUseHtmlPreview(lang, content)) return { kind: "html", lang: l };

  const spec = fenceSpecForLang(l);
  if (spec?.structured) {
    if (isStructuredDraftLang(l) && !looksLikeExplicitDraftContent(content)) {
      return { kind: "prose", lang: l, id: spec.id };
    }
    // Every final answer is the one card; AnswerBlock draws the check only for
    // the server's `verified: true` body.
    if (spec.id === "answer") return { kind: "answer", lang: l, id: spec.id };
    if (spec.id === "math") return { kind: "math", lang: l, id: spec.id };
    if (spec.id === "clock") return { kind: "clock", lang: l, id: spec.id };
    return { kind: "rich", lang: l, id: spec.id };
  }

  if (l === "json" || l === "") {
    const jsonKind = detectJsonRichFenceKind(content);
    if (jsonKind && drawsBareJson(jsonKind)) return { kind: "rich", lang: l, id: jsonKind };
  }

  if (isExplicitCodeLang(lang)) return { kind: "code", lang: l };

  if (allowsContentHeuristic(lang)) {
    // A bare number or short final in a soft fence is math, never an answer card.
    if (looksLikeMathAnswer(content)) return { kind: "math", lang: l };
    if (looksLikeLatexFence(content) || looksLikeMathFenceBody(content)) {
      return { kind: "math", lang: l };
    }
    if (
      isDigitalTimeOnly(content) ||
      isIanaTimezoneOnly(content) ||
      (l === "" && isClockFenceBody(content))
    ) {
      return { kind: "clock", lang: l };
    }
  }

  // CommonMark indented-code of a numbered solve step (`2. **Simplify:**`
  // plus a nested ```math). Never a programming card.
  if (!l && looksLikeMisparsedMarkdownWalkthrough(content)) {
    return { kind: "prose", lang: l };
  }

  if (l === "copy") {
    return shouldRenderAsCopyBlock(lang, content)
      ? { kind: "copy", lang: l, id: "copy" }
      : { kind: "prose", lang: l, id: "copy" };
  }

  if (shouldRenderAsCodeBlock(lang, content)) return { kind: "code", lang: l };
  if (shouldRenderAsCopyBlock(lang, content)) return { kind: "copy", lang: l };
  return { kind: "code", lang: l };
}

export type OpenFencePreviewKind =
  | "answer"
  | "math"
  | "placeholder"
  | "code"
  | "prose"
  | "hide";

/** Same classifier as settled `renderFence` — preview kinds are a subset. */
export function classifyOpenFencePreview(lang: string, body: string): OpenFencePreviewKind {
  const decision = classifyFence(lang, body);
  if (decision.kind === "hide") return "hide";
  // Draft text streams as neutral prose until the fence closes. It must never
  // flash a programming block or a math-style Answer box before becoming a card.
  if (
    decision.kind === "prose" ||
    decision.kind === "copy" ||
    (decision.id != null && isStructuredDraftLang(decision.lang))
  ) {
    return "prose";
  }
  if (decision.kind === "answer") return "answer";
  if (decision.kind === "math") return "math";
  // Server already appended 3D after SMILES; the model's extra open
  // ```molecule3d was a pulsing gray box under "3D Structure" that vanished
  // when the fence closed and the leftover was dropped. Hold nothing.
  if (decision.id === "molecule3d") return "hide";
  // A card drawn from JSON or another machine format (a quiz, a graph, a
  // places list, a ```json that is really a geometry spec) shows nothing raw:
  // half a card's source read as a finished code block. The registry says
  // which bodies are data, so a new card fence is covered when it is added.
  const id = decision.id ?? fenceIdForLang(lang);
  if (id != null && isDataBodyFenceId(id)) return "placeholder";
  // A card around text (a callout, a quote) streams as that text.
  if (decision.kind === "rich") return "prose";
  return "code";
}

export function looksLikeMathMeta(content: string): boolean {
  return /^(Could not render that diagram\.?|Invalid (graph|geometry) block)/i.test(
    content.trim(),
  );
}

export function shouldHideCopyOnCodeFallback(lang: string, content: string): boolean {
  return looksLikeMathMeta(content) || isMathDiagramLang(lang);
}
