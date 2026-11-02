/**
 * A reply as a shared document (Share and PDF): its prose and code as written, maths as
 * maths, and each card the reader cannot open outside Recall (a chart, a graph, a
 * molecule, a calculator) as a one-line label. Control blocks (reminder and settings
 * cards, sources) are left out. Walks the same fences as Copy (`plain.ts`).
 */

import { splitAnswerNotation } from "@/lib/answerNotation";
import {
  documentFormForLang,
  fenceIdForLang,
  fenceSpecForLang,
  isControlFenceLang,
  isMathFenceLang,
  type FenceDocumentBlock,
} from "@/lib/fenceRegistry";
import { fenceToCopyText, mapFenceRegions } from "@/lib/markdown/plain";

/** A card shown in the document as its label alone (each fence's `inDocument` row). */
export type DocumentBlock = FenceDocumentBlock;

/**
 * Where the document goes. Share sends plain text, so a card's lines stay plain lines; the
 * PDF printer joins a paragraph's lines, so there a card's lines end in a hard break.
 */
export type DocumentTarget = "share" | "print";

function cardLines(text: string, target: DocumentTarget): string {
  return target === "print" ? text.replace(/([^\n])\n(?=[^\n])/g, "$1  \n") : text;
}

/** A fence that survives as code: its backticks outnumber any run inside it. */
function codeFence(lang: string, body: string): string {
  const longest = Math.max(2, ...[...body.matchAll(/`+/g)].map((run) => run[0].length));
  const marks = "`".repeat(longest + 1);
  return `${marks}${lang}\n${body}\n${marks}`;
}

function answerText(body: string): string {
  const { notation, body: answer } = splitAnswerNotation(body);
  // A chemistry answer, or one written as a sentence with its own $…$, is text.
  if (notation === "chemistry" || answer.includes("$")) return answer;
  return codeFence("math", answer);
}

function documentFence(
  lang: string,
  body: string,
  label: (block: DocumentBlock) => string,
  target: DocumentTarget,
): string {
  const trimmed = body.replace(/\n$/, "").trim();
  const id = fenceIdForLang(lang);
  const form = documentFormForLang(lang);
  // A long-division or column sum reads as its worked lines, a quiz as its question.
  if (form === "copyText") return cardLines(fenceToCopyText(lang, body), target);
  if (form) return label(form);
  if (isControlFenceLang(lang)) return "";
  if (id === "answer") return answerText(trimmed);
  if (isMathFenceLang(lang)) return codeFence("math", trimmed);
  // A drafted email, a callout or a list of steps is text the reader reads as it is.
  if (fenceSpecForLang(lang)) return trimmed;
  if (lang.startsWith("callout-")) return trimmed;
  return codeFence(lang, body.replace(/\n$/, ""));
}

/** The reply as Share and PDF show it; `label` names a card left out ("[Chart]"). */
export function markdownToDocumentText(
  markdown: string,
  label: (block: DocumentBlock) => string,
  target: DocumentTarget = "share",
): string {
  return mapFenceRegions(
    markdown,
    (prose) => prose,
    (lang, body) => documentFence(lang, body, label, target),
  )
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
