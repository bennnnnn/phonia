/**
 * What a lesson card shows from its fence, read once for the card and for its text, so copy,
 * read-aloud and a shared chat say what the screen shows and never a quiz's answer.
 */

import { isUnfinishedJson } from "@/lib/jsonFence";
import {
  type ArrayFence,
  arrayText,
  type LooseArray,
  type LooseQuiz,
  looseArray,
  looseQuiz,
  parseArrayFence,
  parseQuizFence,
  plainFenceText,
  type QuizFence,
  quizText,
} from "@/lib/lesson/lessonFences";

/**
 * What a lesson card draws from its fence, in order: the card its JSON parses to, plain text
 * written in its place, nothing while JSON streams, or the words broken JSON still holds.
 */
type CardBody<Card, Loose> =
  | { kind: "card"; card: Card }
  | { kind: "plain"; text: string }
  | { kind: "loose"; loose: Loose };

function cardBody<Card, Loose>(
  content: string,
  parse: (content: string) => Card | null,
  loose: (content: string) => Loose | null,
): CardBody<Card, Loose> | null {
  const card = parse(content);
  if (card) return { kind: "card", card };
  const text = plainFenceText(content);
  if (text) return { kind: "plain", text };
  if (isUnfinishedJson(content)) return null;
  const read = loose(content);
  return read ? { kind: "loose", loose: read } : null;
}

export function quizBody(content: string): CardBody<QuizFence, LooseQuiz> | null {
  return cardBody(content, parseQuizFence, looseQuiz);
}

export function arrayBody(content: string): CardBody<ArrayFence, LooseArray> | null {
  return cardBody(content, parseArrayFence, looseArray);
}

/** A broken list's values as its card shows them. */
export function looseArrayValues(list: LooseArray): string {
  return `[${list.values.join(", ")}]`;
}

/** A quiz as copy, speech and a shared chat read it: what its card shows before "Check answer". */
export function quizCardText(content: string): string {
  const body = quizBody(content);
  if (!body) return "";
  if (body.kind === "plain") return body.text;
  return quizText(body.kind === "card" ? body.card : body.loose);
}

/** A list as copy, speech and a shared chat read it: its values, as its card shows them. */
export function arrayCardText(content: string): string {
  const body = arrayBody(content);
  if (!body) return "";
  if (body.kind === "plain") return body.text;
  return body.kind === "card" ? arrayText(body.card) : looseArrayValues(body.loose);
}
