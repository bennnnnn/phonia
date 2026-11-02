/**
 * Lesson cards the model writes as JSON fences.
 *
 * ```quiz {"label": "Exercise 1", "question": "...", "code": "...", "lang": "python",
 *          "options": ["...", "..."], "answer": 1, "explanation": "..."}
 * ```array {"title": "A list is a row of numbered boxes.", "values": [2, 7, 11, 15],
 *           "highlight": [0, 1], "caption": "2 + 7 = 9",
 *           "note": "We return indexes, not the numbers."}
 *
 * Both parse to null when the fence is not usable; the loose readers below
 * then pull out whatever words it still holds.
 */

import { parseJsonRecord } from "@/lib/jsonFence";
import { scanFences } from "@/lib/mdFenceScan";

export type QuizFence = {
  /** The pill at the top of the card, such as "Exercise 1". */
  label: string | null;
  question: string;
  /** Code the question is about, drawn inside the card. */
  code: string | null;
  codeLang: string;
  options: string[];
  /** 0-based index into `options`. */
  answer: number;
  explanation: string;
};

type ArrayValue = string | number | boolean | null;

export type ArrayFence = {
  /** The list's name, for copy and speech ("nums = [2, 7, 11, 15]"). */
  name: string | null;
  /** A line above the boxes: "Think of a Python list as a row of numbered boxes." */
  title: string | null;
  values: ArrayValue[];
  highlight: number[];
  /** A short line under the boxes, such as "2 + 7 = 9". */
  caption: string | null;
  /** One sentence under the caption. */
  note: string | null;
};

/** A quiz explanation: prose, with any fenced code drawn as a code block. */
type ExplanationPart =
  | { kind: "text"; text: string }
  | { kind: "code"; lang: string; code: string };

const MAX_OPTIONS = 6;
const MAX_CELLS = 24;
const LETTERS = "ABCDEF";

function trimmed(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** The answer as an index: 1, "1", "B", "B)" or the option's own text. */
function answerIndex(answer: unknown, options: string[]): number {
  if (typeof answer === "number" && Number.isInteger(answer)) return answer;
  const text = trimmed(answer);
  if (/^\d+$/.test(text)) return Number(text);
  const letter = text.match(/^([A-F])[).:]?$/i);
  if (letter) return LETTERS.indexOf(letter[1]!.toUpperCase());
  return options.findIndex((option) => option === text);
}

export function parseQuizFence(content: string): QuizFence | null {
  const data = parseJsonRecord(content);
  if (!data) return null;
  const question = trimmed(data.question);
  const options = Array.isArray(data.options)
    ? data.options.map((option) =>
        typeof option === "number" ? String(option) : trimmed(option),
      )
    : [];
  if (!question || options.length < 2 || options.length > MAX_OPTIONS)
    return null;
  if (options.some((option) => !option)) return null;
  const answer = answerIndex(data.answer, options);
  if (answer < 0 || answer >= options.length) return null;
  const code = typeof data.code === "string" ? data.code.replace(/^\n+|\s+$/g, "") : "";
  return {
    label: trimmed(data.label) || null,
    question,
    code: code || null,
    codeLang: trimmed(data.lang) || "python",
    options,
    answer,
    explanation: trimmed(data.explanation),
  };
}

function isCell(value: unknown): value is ArrayValue {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

export function parseArrayFence(content: string): ArrayFence | null {
  const data = parseJsonRecord(content);
  if (!data || !Array.isArray(data.values)) return null;
  const values = data.values;
  if (values.length === 0 || values.length > MAX_CELLS || !values.every(isCell))
    return null;
  const highlight = Array.isArray(data.highlight)
    ? data.highlight.filter(
        (index): index is number =>
          Number.isInteger(index) &&
          (index as number) >= 0 &&
          (index as number) < values.length,
      )
    : [];
  return {
    name: trimmed(data.name) || null,
    title: trimmed(data.title) || null,
    values,
    highlight,
    caption: trimmed(data.caption) || null,
    note: trimmed(data.note) || null,
  };
}

/** How a cell reads: strings quoted, the rest as written. */
export function formatCell(value: ArrayValue): string {
  return typeof value === "string" ? JSON.stringify(value) : String(value);
}

/** "nums = [2, 7, 11, 15]" for copy and speech. */
export function arrayText(fence: ArrayFence): string {
  const list = `[${fence.values.map(formatCell).join(", ")}]`;
  return fence.name ? `${fence.name} = ${list}` : list;
}

/** "A)", "B)", ... and "7)" past the sixth option. */
export function optionLetter(index: number): string {
  return `${LETTERS[index] ?? index + 1})`;
}

/** The question and lettered options as plain text, for copy and speech. Never the answer. */
export function quizText(fence: Pick<QuizFence, "question" | "code" | "options">): string {
  const options = fence.options.map((option, i) => `${optionLetter(i)} ${option}`);
  const code = fence.code ? [fence.code] : [];
  return [fence.question, ...code, ...options].filter(Boolean).join("\n");
}

/** Split an explanation into prose and fenced code, in order. */
export function explanationParts(text: string): ExplanationPart[] {
  const parts: ExplanationPart[] = [];
  let last = 0;
  for (const span of scanFences(text)) {
    if (!span.closed) continue;
    const before = text.slice(last, span.start).trim();
    if (before) parts.push({ kind: "text", text: before });
    parts.push({
      kind: "code",
      lang: span.info.split(/\s/)[0] || "text",
      code: span.body.replace(/\s+$/, ""),
    });
    last = span.end;
  }
  const rest = text.slice(last).trim();
  if (rest) parts.push({ kind: "text", text: rest });
  return parts;
}

/**
 * A quiz fence that does not parse still has a question and options to read.
 * The model may break the JSON (a raw newline, a trailing comma) or give an
 * answer the options do not hold; the learner sees the words, not an error.
 */
export type LooseQuiz = {
  label: string | null;
  question: string;
  code: string | null;
  codeLang: string;
  options: string[];
  explanation: string;
};

/** A list fence that does not parse: its values as written, and its lines. */
export type LooseArray = {
  values: string[];
  title: string | null;
  caption: string | null;
  note: string | null;
};

const JSON_STRING = /"((?:[^"\\]|\\.)*)"/y;
const JSON_SCALAR = /-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null/y;

function decodeJsonString(raw: string): string {
  try {
    return JSON.parse(`"${raw}"`) as string;
  } catch {
    return raw.replace(/\\n/g, "\n").replace(/\\"/g, '"');
  }
}

function keyStart(content: string, key: string): number {
  const at = content.search(new RegExp(`"${key}"\\s*:`));
  if (at < 0) return -1;
  return content.indexOf(":", at) + 1;
}

function skipBlank(content: string, index: number): number {
  let i = index;
  while (i < content.length && /\s/.test(content[i]!)) i += 1;
  return i;
}

/** The string after `"key":`, read even when the JSON around it is broken. */
function looseString(content: string, key: string): string {
  const start = keyStart(content, key);
  if (start <= 0) return "";
  JSON_STRING.lastIndex = skipBlank(content, start);
  const match = JSON_STRING.exec(content);
  return match ? decodeJsonString(match[1]!).trim() : "";
}

/** The items of the array after `"key":`, each as text, in order. */
function looseItems(content: string, key: string): string[] {
  const start = keyStart(content, key);
  if (start <= 0) return [];
  let i = skipBlank(content, start);
  if (content[i] !== "[") return [];
  i += 1;
  const items: string[] = [];
  while (i < content.length) {
    i = skipBlank(content, i);
    const char = content[i];
    if (char === "]" || char === undefined) break;
    if (char === ",") {
      i += 1;
      continue;
    }
    if (char === '"') {
      JSON_STRING.lastIndex = i;
      const match = JSON_STRING.exec(content);
      if (!match) break;
      items.push(decodeJsonString(match[1]!));
      i = JSON_STRING.lastIndex;
      continue;
    }
    JSON_SCALAR.lastIndex = i;
    const scalar = JSON_SCALAR.exec(content);
    if (!scalar) break;
    items.push(scalar[0]);
    i = JSON_SCALAR.lastIndex;
  }
  return items;
}

export function looseQuiz(content: string): LooseQuiz | null {
  const question = looseString(content, "question");
  const options = looseItems(content, "options").map((option) => option.trim()).filter(Boolean);
  if (!question && options.length === 0) return null;
  return {
    label: looseString(content, "label") || null,
    question,
    code: looseString(content, "code") || null,
    codeLang: looseString(content, "lang") || "python",
    options,
    explanation: looseString(content, "explanation"),
  };
}

export function looseArray(content: string): LooseArray | null {
  const values = looseItems(content, "values");
  if (values.length === 0) return null;
  return {
    values,
    title: looseString(content, "title") || null,
    caption: looseString(content, "caption") || null,
    note: looseString(content, "note") || null,
  };
}

/**
 * A lesson card's own JSON member (`"answer":`, `"values":`): text holding one is the card's
 * JSON, even after a line of prose. Other quoted words (`x = {"a": 1}`) stay plain text.
 */
const CARD_MEMBER = /"(?:question|questions|options|answer|explanation|values)"\s*:/;

/**
 * Text in a lesson fence that is not JSON at all, such as a question written out. A body
 * holding JSON after prose is not plain: drawn as text it would show the quiz's answer key.
 */
export function plainFenceText(content: string): string | null {
  const text = content.trim();
  if (!text || text.startsWith("{") || text.startsWith("[") || CARD_MEMBER.test(text)) return null;
  return text;
}
