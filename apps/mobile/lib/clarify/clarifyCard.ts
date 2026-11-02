/**
 * The ```clarify card a reply asks with (docs/clarify.md): read from its JSON, and the
 * user's picks written back as their next message.
 *
 * The server checks the card before it is saved (apps/api/app/modules/chat/clarify_card.py)
 * and reads the picks the next turn (clarify_turn.answers_card): the card's request, then
 * "Label: pick." for each question, then its closing, the label exactly as the card has
 * it. This reader is lenient where the server already normalised, and strict where a wrong
 * shape would draw a broken card.
 */
import { parseJsonRecord } from "@/lib/jsonFence";
import { collectClosedFenceBodies } from "@/lib/mdFenceScan";

export type ClarifyQuestion = {
  id: string;
  /** The short name the sent message uses ("Main priority"). */
  label: string;
  /** What the card shows ("What matters most to you?"). */
  question: string;
  /** The choices as the card draws them, emoji first ("💰 Making money"). */
  options: string[];
  /** The same choices as the sent message says them ("Making money"), one per option. */
  values: string[];
};

export type ClarifyCard = {
  questions: ClarifyQuestion[];
  /** The sent message's first sentence ("Recommend the best country for me."); may be empty. */
  request: string;
  /** Its last sentence ("Compare the strongest options with practical pros and cons."); may be empty. */
  closing: string;
  /** The button ("Find my best country"); empty means the app's own "Submit". */
  submit: string;
};

/** Each question's pick, by question id: the index of the chosen option. */
export type ClarifyAnswers = Record<string, number>;

const MAX_QUESTIONS = 3;
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 8;
// A pick that already ends a sentence takes no full stop of its own (Amharic ends with ። or ፧).
const SENTENCE_END = /[.!?…。！？።፧]$/;

/** One line of text: trimmed, runs of whitespace (newlines too) as one space. */
function oneLine(value: unknown): string {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function readOptions(raw: unknown): string[] | null {
  if (!Array.isArray(raw)) return null;
  const seen = new Set<string>();
  const options: string[] = [];
  for (const item of raw) {
    const text = oneLine(item);
    if (!text || seen.has(text.toLowerCase())) continue;
    seen.add(text.toLowerCase());
    options.push(text);
  }
  return options.length >= MIN_OPTIONS && options.length <= MAX_OPTIONS ? options : null;
}

function readQuestion(raw: unknown, index: number): ClarifyQuestion | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const record = raw as Record<string, unknown>;
  const question = oneLine(record.question);
  const label = oneLine(record.label) || question;
  const options = readOptions(record.options);
  if (!question || !label || !options) return null;
  // The server writes a value per option; a card saved before it had none says the option.
  const values = Array.isArray(record.values) ? record.values.map(oneLine) : [];
  const fitting = values.length === options.length && values.every(Boolean);
  return {
    id: oneLine(record.id) || `q${index + 1}`,
    label,
    question,
    options,
    values: fitting ? values : options,
  };
}

/** The card in a fence body, or null when it is not one the phone can draw. */
export function parseClarifyCard(content: string): ClarifyCard | null {
  const data = parseJsonRecord(content.trim());
  if (!data || !Array.isArray(data.questions)) return null;
  if (data.questions.length === 0 || data.questions.length > MAX_QUESTIONS) return null;
  const questions: ClarifyQuestion[] = [];
  for (const [index, raw] of data.questions.entries()) {
    const question = readQuestion(raw, index);
    if (!question) return null;
    questions.push(question);
  }
  const ids = new Set(questions.map((question) => question.id));
  if (ids.size !== questions.length) {
    questions.forEach((question, index) => (question.id = `q${index + 1}`));
  }
  return {
    questions,
    request: oneLine(data.request),
    closing: oneLine(data.closing),
    submit: oneLine(data.submit),
  };
}

/**
 * True when a reply asks with a card. Its follow-up is the card itself, so suggested
 * questions under it ("What is your budget?") only repeat what it asks.
 */
export function asksWithCard(content: string): boolean {
  return collectClosedFenceBodies(content, "clarify").some((body) => parseClarifyCard(body) !== null);
}

/** What a live card starts on: the first choice of every question, the likeliest one. */
export function initialClarifyAnswers(card: ClarifyCard): ClarifyAnswers {
  return Object.fromEntries(card.questions.map((question) => [question.id, 0]));
}

/**
 * The message the button sends, one paragraph: the card's request, "Label: pick." for
 * each question in the card's order, then its closing. A question with no pick sends
 * its first choice, as the card shows it.
 */
export function clarifyMessage(card: ClarifyCard, answers: ClarifyAnswers): string {
  const picks = card.questions.map((question) => {
    const value = question.values[answers[question.id] ?? 0] ?? question.values[0];
    return `${question.label}: ${value}${SENTENCE_END.test(value) ? "" : "."}`;
  });
  return [card.request, ...picks, card.closing].filter(Boolean).join(" ");
}

/** Where the pick after "Label:" starts in the lower-cased message, or -1. */
function pickStart(lower: string, label: string): number {
  const key = label.toLowerCase();
  for (let at = lower.indexOf(key); at >= 0; at = lower.indexOf(key, at + 1)) {
    if (at > 0 && /\w/.test(lower[at - 1])) continue;
    const colon = /^[^\S\n]*:[^\S\n]*/.exec(lower.slice(at + key.length));
    if (colon) return at + key.length + colon[0].length;
  }
  return -1;
}

/** The choice a pick starts with, longest first so "Yes, I'm revising" beats "Yes". */
function pickedIndex(question: ClarifyQuestion, rest: string): number | null {
  let best: number | null = null;
  for (const [index, value] of question.values.entries()) {
    const key = value.toLowerCase();
    if (!rest.startsWith(key) || /\w/.test(rest.charAt(key.length))) continue;
    if (best == null || key.length > question.values[best].length) best = index;
  }
  return best;
}

/**
 * The picks a sent message holds, read back onto the card it answered: every label is
 * there with a pick after it (as the server reads it), in the sentence this phone sends or
 * the one line per question older phones sent. Null when the message is anything else,
 * something typed instead. A pick that is none of the card's choices is left unticked.
 */
export function answersFromMessage(card: ClarifyCard, message: string): ClarifyAnswers | null {
  const lower = message.toLowerCase();
  const answers: ClarifyAnswers = {};
  for (const question of card.questions) {
    const start = pickStart(lower, question.label);
    // The pick is on the label's own line: "Label:" then a blank line is no pick.
    if (start < 0 || !lower.slice(start).split("\n")[0]!.trim()) return null;
    const index = pickedIndex(question, lower.slice(start));
    if (index != null) answers[question.id] = index;
  }
  return answers;
}

/** What Copy and Read aloud make of a card: each question and its choices. */
export function clarifyText(card: ClarifyCard): string {
  return card.questions
    .map((question) => `${question.question} (${question.values.join(" / ")})`)
    .join("\n");
}
