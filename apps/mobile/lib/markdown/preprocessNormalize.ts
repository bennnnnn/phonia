import { parseFenceLang } from "@/lib/codeHighlight";
import { readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { isWorkedReply, lawHeading, WORKOUT_HEADINGS } from "@/lib/markdown/workoutSection";
import { applyOutsideFences, fencedLines, mapClosedFences, readFenceMarker } from "@/lib/mdFenceScan";

const DETAILS_FENCE_LANGS = new Set(["details", "collapse", "summary"]);
const DETAILS_WITH_SUMMARY_RE =
  /<details\b[^>]*>\s*<summary>([\s\S]*?)<\/summary>\s*([\s\S]*?)<\/details>/gi;
const DETAILS_BARE_RE = /<details\b[^>]*>([\s\S]*?)<\/details>/gi;

/**
 * Models occasionally leave padding before a closing bold delimiter:
 * `**Why this works: **`. CommonMark treats that closer as literal text, so
 * the user sees the raw `**`. Trim only delimiter-adjacent horizontal space,
 * and never touch code fences.
 *
 * Delimiters pair in order on a line, outside inline code: the closer of one
 * span and the opener of the next (`**60** and at **40**`) are not a pair, so
 * the space before an opener stays (it used to read `at**40**`).
 */
export function trimBoldDelimiterWhitespace(content: string): string {
  return applyOutsideFences(content, (prose) => prose.split("\n").map(trimBoldLine).join("\n"));
}

function trimBoldLine(line: string): string {
  if (!line.includes("**")) return line;
  let out = "";
  let copied = 0;
  let openAt = -1;
  let index = 0;
  while (index < line.length) {
    const codeEnd = line[index] === "`" ? readInlineCodeSpan(line, index) : null;
    if (codeEnd != null || !line.startsWith("**", index)) {
      index = codeEnd ?? index + 1;
      continue;
    }
    if (openAt >= 0) {
      const inner = line.slice(openAt + 2, index);
      if (!inner.includes("*") && /\S[ \t]+$/.test(inner)) {
        out += line.slice(copied, openAt + 2) + inner.trimEnd();
        copied = index;
      }
    }
    openAt = openAt >= 0 ? -1 : index;
    index += 2;
  }
  return out + line.slice(copied);
}

// A bold line alone, then a line of its own (not a blank one). Workout headings stay.
const STANDALONE_BOLD_LINE = new RegExp(
  String.raw`^(\s*\*\*(?!\d+[.)]\s)(?!(?:${WORKOUT_HEADINGS.join("|")}|Answer \([a-h]\)):?\*\*)[^*\n]+\*\*(?:[ \t]*` +
    "`[^`\\n]+`" +
    String.raw`)?\s*)\n(?!\n)`,
  "gm",
);

// A workout heading alone on its line with a line of its own under it (no blank line).
const WORKOUT_HEADING_LINE = new RegExp(
  String.raw`^(\s*\*\*(?:${WORKOUT_HEADINGS.join("|")}|Answer \([a-h]\)):?\*\*)[ \t]*\n(?=\S)`,
  "gm",
);

/** Keep a bold-only teaching label, or a label and its code, on its own
 * visual row.
 *
 * CommonMark treats one newline as a space, so ``**Substitute**\n$x=2$``
 * became one crowded line on iPhone, and a line-by-line walk-through
 * (``**Line 1:** `total = 0` `` then its explanation) ran the explanation on
 * after the code. A blank line preserves the author's intended step
 * structure and gives tall native fractions/radicals their own row. List
 * labels and fenced examples are deliberately untouched. A workout heading
 * (Given, Required, Formula, Substitution, Steps, Answer) keeps its lines: the
 * workout renderer gives each line its own row. So does a law's name heading
 * its formulas in a worked reply ("**Constant acceleration**" over `$v = u + at$`).
 */
export function separateStandaloneBoldLines(content: string): string {
  return applyOutsideFences(content, (prose) => {
    const worked = isWorkedReply(prose);
    // A heading's lines start on the next row: written with a plain line break (as a
    // model does), "**Substitution**" and its first line ran together on one row.
    const headed = prose.replace(WORKOUT_HEADING_LINE, "$1  \n");
    return headed.replace(STANDALONE_BOLD_LINE, (line: string, head: string, offset: number) => {
      const next = headed.slice(offset + line.length).split("\n", 1)[0] ?? "";
      const name = head.trim().replace(/^\*\*|\*\*$/g, "");
      return worked && lawHeading(name, next) ? `${head.trimEnd()}  \n` : `${head}\n\n`;
    });
  });
}

/** Numbered/bulleted lists and headings — never code fences. */
export function looksLikeMarkdownListProse(content: string): boolean {
  const lines = content
    .trim()
    .split("\n")
    .filter((l) => l.trim());
  if (lines.length === 0) return false;
  const proseLines = lines.filter((line) => {
    const t = line.trim();
    return (
      /^#{1,6}\s/.test(t) ||
      /^\d+\.\s+\*\*/.test(t) ||
      /^[-*]\s+\*\*/.test(t) ||
      /^\d+\.\s+[A-Z]/.test(t)
    );
  });
  return proseLines.length >= 1;
}

/**
 * A line that is just ":" (a stranded colon) renders as a lone "two dots"
 * on its own line — the model put it on a separate line after a bold step
 * header (``**Multiply**\n:\n$3 \times 2 = 6$``). Merge it onto the previous
 * line so it renders inline (``**Multiply**:``) instead of stranded.
 *
 * Also handles stranded `;` (same pattern — the model puts the semicolon
 * on its own line after a step header or label).
 */
export function mergeStrandedColons(content: string): string {
  const lines = content.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]!;
    const trimmed = line.trim();
    if (trimmed === ":" || trimmed === ";") {
      if (out.length > 0) {
        const prev = out[out.length - 1]!;
        const prevTrimmed = prev.trim();
        // Don't glue punctuation onto a fence closer, table row, or heading.
        if (
          readFenceMarker(prevTrimmed) != null ||
          prevTrimmed.startsWith("|") ||
          /^#{1,6}\s/.test(prevTrimmed)
        ) {
          out.push(line);
        } else {
          out[out.length - 1] = prev.replace(/\s*$/, "") + trimmed;
        }
      } else {
        out.push(line);
      }
    } else {
      out.push(line);
    }
  }
  return out.join("\n");
}

/**
 * Models sometimes put a list label and its value on separate lines:
 * `- **Chemical Formula**\n  : O₂`. The leading colon becomes a conspicuous
 * standalone glyph in React Native. Keep the intended two-line layout while
 * dropping only that decorative colon.
 */
export function stripBoldListLabelContinuationColons(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  for (const [index, originalLine] of lines.entries()) {
    if (fenced[index]) {
      out.push(originalLine);
      continue;
    }

    const previous = out[out.length - 1]?.trim() ?? "";
    const previousIsBoldListLabel =
      /^(?:[-*+]|\d+[.)])\s+\*\*[^*\n]+\*\*\s*$/.test(previous);
    if (previousIsBoldListLabel) {
      out.push(originalLine.replace(/^(\s*):(?:\s+|$)/, "$1"));
      continue;
    }
    out.push(originalLine);
  }
  return out.join("\n");
}

/**
 * Models glue an ATX heading onto the previous sentence
 * (``$y=3x+4$: ### Explanation``). CommonMark only recognizes headings at
 * line start, so the hashes leak as literal ``###``. Break them out.
 */
export function breakMidlineAtxHeadings(content: string): string {
  const lines = content.split("\n");
  const fenced = fencedLines(content);
  const out: string[] = [];
  for (const [index, line] of lines.entries()) {
    if (fenced[index] || !line.includes("#")) {
      out.push(line);
      continue;
    }
    const split = line.replace(/([^\n#])[ \t]*(#{1,6}[ \t]+\S)/g, "$1\n\n$2");
    if (split === line) {
      out.push(line);
    } else {
      out.push(...split.split("\n"));
    }
  }
  return out.join("\n");
}

function boldDetailsTitle(title: string): string {
  // Drop each bracket on its own. Stripping a whole tag once lets
  // `<scr<script>ipt>` reassemble into `<script`.
  const cleaned = title
    .replace(/[<>]/g, "")
    .replace(/\*\*/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "";
  return `**${cleaned}**`;
}

function detailsToMarkdown(title: string, body: string): string {
  const heading = boldDetailsTitle(title);
  const text = body.replace(/^\n+/, "").replace(/\n+$/, "");
  if (heading && text) return `\n${heading}\n\n${text}\n`;
  if (heading) return `\n${heading}\n`;
  if (text) return `\n${text}\n`;
  return "\n";
}

function detailsFenceToMarkdown(info: string, body: string): string {
  const lang = parseFenceLang(info);
  const titleFromInfo = info.trim().slice(lang.length).trim();
  if (titleFromInfo) return detailsToMarkdown(titleFromInfo, body);
  const nl = body.indexOf("\n");
  if (nl === -1) return detailsToMarkdown(body.trim(), "");
  return detailsToMarkdown(body.slice(0, nl), body.slice(nl + 1));
}

/** Legacy collapsed answers become a bold title plus normal Markdown. */
export function convertDetailsBlocks(content: string): string {
  const unwrapped = mapClosedFences(content, (info, body, original) => {
    const lang = parseFenceLang(info);
    if (!DETAILS_FENCE_LANGS.has(lang)) return original;
    return detailsFenceToMarkdown(info, body);
  });
  return applyOutsideFences(unwrapped, (prose) => {
    DETAILS_WITH_SUMMARY_RE.lastIndex = 0;
    DETAILS_BARE_RE.lastIndex = 0;
    const withSummary = prose.replace(
      DETAILS_WITH_SUMMARY_RE,
      (_m, title: string, body: string) => detailsToMarkdown(title, body),
    );
    DETAILS_BARE_RE.lastIndex = 0;
    return withSummary.replace(DETAILS_BARE_RE, (_m, body: string) =>
      detailsToMarkdown("", body),
    );
  });
}

/** Vega specs are retagged so they render as charts. */
const VEGA_FENCE_LANGS = new Set(["", "json", "vega", "vega-lite", "chart", "plot"]);
const VEGA_SCHEMA_MARKER = '"$schema"';
const VEGA_SCHEMA_HOST = "vega.github.io/schema/";

function fenceBodyLooksLikeVega(body: string): boolean {
  return (
    body.includes(VEGA_SCHEMA_MARKER) &&
    body.includes(VEGA_SCHEMA_HOST) &&
    body.includes("{") &&
    body.includes("}")
  );
}

/** Retag ```json/vega… fences that hold Vega specs — linear fence walk, no nested regex. */
export function retagVegaFences(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const open = src.indexOf("```", i);
    if (open === -1) {
      out += src.slice(i);
      break;
    }
    out += src.slice(i, open);
    const afterOpen = open + 3;
    const nl = src.indexOf("\n", afterOpen);
    if (nl === -1) {
      out += src.slice(open);
      break;
    }
    const lang = src.slice(afterOpen, nl).trim().toLowerCase();
    const close = src.indexOf("```", nl + 1);
    if (close === -1) {
      out += src.slice(open);
      break;
    }
    const body = src.slice(nl + 1, close);
    if (VEGA_FENCE_LANGS.has(lang) && fenceBodyLooksLikeVega(body) && lang !== "vega-lite") {
      out += "```vega-lite\n" + body.trim() + "\n```";
    } else {
      out += src.slice(open, close + 3);
    }
    i = close + 3;
  }
  return out;
}

/**
 * Wrap bare Vega-Lite JSON objects (not already fenced) so ChartBlock can render them.
 * Scans for `{` + `"$schema"` + vega host, then walks braces — no `[\s\S]*?` pump.
 */
export function wrapBareVegaJson(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const start = src.indexOf("{", i);
    if (start === -1) {
      out += src.slice(i);
      break;
    }
    const atBoundary = start === 0 || (start >= 2 && src.slice(start - 2, start) === "\n\n");
    if (!atBoundary) {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    // Inside an open ``` fence? leave alone (retagVegaFences already handled).
    let fenceMarks = 0;
    for (let f = src.indexOf("```"); f !== -1 && f < start; f = src.indexOf("```", f + 3)) {
      fenceMarks += 1;
    }
    if (fenceMarks % 2 === 1) {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    let k = start + 1;
    while (k < src.length && (src[k] === " " || src[k] === "\t" || src[k] === "\n" || src[k] === "\r")) {
      k += 1;
    }
    if (!src.startsWith(VEGA_SCHEMA_MARKER, k)) {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    const hostAt = src.indexOf(VEGA_SCHEMA_HOST, k);
    if (hostAt === -1 || hostAt - k > 120) {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    let depth = 0;
    let end = -1;
    const scanLimit = Math.min(src.length, start + 100_000);
    for (let j = start; j < scanLimit; j += 1) {
      const ch = src[j];
      if (ch === "{") depth += 1;
      else if (ch === "}") {
        depth -= 1;
        if (depth === 0) {
          end = j;
          break;
        }
      }
    }
    // Prior regex required a newline immediately before the closing `}`.
    if (end === -1 || end === 0 || src[end - 1] !== "\n") {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    const body = src.slice(start, end + 1);
    if (!fenceBodyLooksLikeVega(body)) {
      out += src.slice(i, start + 1);
      i = start + 1;
      continue;
    }
    out += src.slice(i, start);
    out += `\n\n\`\`\`vega-lite\n${body.trim()}\n\`\`\`\n\n`;
    i = end + 1;
  }
  return out;
}
