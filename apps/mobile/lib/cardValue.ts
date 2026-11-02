/**
 * What an answer card holds: the final answer, never the calculation before it.
 *
 * A checked line such as `4 × 4 = 16` or `5! = 5 × 4 × 3 × 2 × 1 = 120` is working: the
 * card shows `16` and `120`. Only arithmetic on plain numbers counts as working. A named
 * answer stays whole (`x = 1`, `pH = 2.00`, `x = 2 \text{ or } x = 3`), and so does one
 * value written two ways (`\frac{5}{6} \approx 0.833`).
 *
 * The server writes new cards this way (apps/api/app/services/card_value.py); this
 * twin reads every card the same, old ones too. Both are held to
 * docs/fixtures/answer_card_cases.json.
 */

const APPROX = new Set(["\\approx", "≈"]);
// Spacing and sizing commands that change nothing a reader computes.
const SPACING = /\\(?:left|right|[,;:! ])/g;
const OPERATOR_COMMANDS = /\\(?:times|div|cdot)(?![A-Za-z])/g;
// A fraction of two numbers is one value, like 0.5: an operand, not an operation.
const NUMBER_FRACTION = /\\[dt]?frac\{\s*\d+(?:\.\d+)?\s*\}\{\s*\d+(?:\.\d+)?\s*\}/g;
const ARITHMETIC = /^[0-9.()[\]{}+\-−×÷·*/^!\s]+$/;
const OPERATION = /[+\-−×÷·*/^!]/;
// Several answers or a layout: never split.
const LIST = /[,;&]|\\\\|\\text|\\begin|\\quad/;

export function splitWorking(value: string): { working: string | null; answer: string } {
  if (value.includes("\n") || LIST.test(value.replaceAll("{,}", ""))) {
    return { working: null, answer: value };
  }
  const { sides, relations } = relationsOf(value);
  let dropped = 0;
  while (dropped < sides.length - 1 && isArithmetic(sides[dropped]!)) dropped += 1;
  if (dropped === 0) return { working: null, answer: value };
  let working = sides[0]!;
  for (let index = 1; index < dropped; index += 1) {
    working += ` ${relations[index - 1]} ${sides[index]}`;
  }
  let answer = sides[dropped]!;
  for (let index = dropped + 1; index < sides.length; index += 1) {
    answer += ` ${relations[index - 1]} ${sides[index]}`;
  }
  if (APPROX.has(relations[dropped - 1]!)) answer = `\\approx ${answer}`;
  return { working, answer };
}

/** The card's value without the calculation that led to it. */
export function finalAnswerOnly(value: string): string {
  return splitWorking(value).answer;
}

/** The sides of `a = b ≈ c` and the relations between them, outside braces. */
function relationsOf(value: string): { sides: string[]; relations: string[] } {
  const sides: string[] = [];
  const relations: string[] = [];
  let depth = 0;
  let start = 0;
  let index = 0;
  while (index < value.length) {
    const char = value[index]!;
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    const relation = depth === 0 ? relationAt(value, index) : null;
    if (relation == null) {
      index += 1;
      continue;
    }
    sides.push(value.slice(start, index).trim());
    relations.push(relation);
    index += relation.length;
    start = index;
  }
  sides.push(value.slice(start).trim());
  return { sides, relations };
}

function relationAt(value: string, index: number): string | null {
  if (value.startsWith("\\approx", index) && !/[A-Za-z]/.test(value[index + 7] ?? "")) {
    return "\\approx";
  }
  const char = value[index];
  if (char === "≈") return char;
  // Not the = of <=, >=, != or ==.
  if (char === "=" && !["<", ">", "!", "="].includes(value[index - 1] ?? "")) {
    return value[index + 1] === "=" ? null : char;
  }
  return null;
}

/** Arithmetic on plain numbers: `4 × 4`, `5!`, `\frac{1}{2} + \frac{1}{3}`. */
function isArithmetic(side: string): boolean {
  const plain = side.replace(SPACING, " ").replaceAll("{,}", "");
  const text = plain.replace(OPERATOR_COMMANDS, "×").replace(NUMBER_FRACTION, "1");
  if (!text.trim() || !ARITHMETIC.test(text) || !/\d/.test(text)) return false;
  // A leading sign is part of the number: -8 is a value.
  return OPERATION.test(text.trim().replace(/^[+\-−]+/, ""));
}
