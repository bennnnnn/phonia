import {
  caretInGroup,
  readBraceGroup,
  readDelimGroup,
  readSetBrace,
  type LatexGroup,
  type TextSelection,
} from "@/lib/math/keyboardSymbols";

export type DraftNode =
  | { kind: "text"; start: number; end: number }
  | { kind: "frac"; start: number; end: number; num: LatexGroup; den: LatexGroup }
  | { kind: "sqrt"; start: number; end: number; index?: LatexGroup; body: LatexGroup }
  | { kind: "script"; start: number; end: number; mark: "^" | "_"; body: LatexGroup }
  | { kind: "binom"; start: number; end: number; n: LatexGroup; k: LatexGroup }
  | { kind: "vec"; start: number; end: number; body: LatexGroup }
  | { kind: "abs"; start: number; end: number; body: LatexGroup }
  | { kind: "brace"; start: number; end: number; body: LatexGroup }
  | { kind: "group"; start: number; end: number; open: string; close: string; body: LatexGroup };

function cmdAt(text: string, i: number, cmd: string): boolean {
  if (!text.startsWith(cmd, i)) return false;
  const next = text[i + cmd.length];
  return !next || !/[A-Za-z]/.test(next);
}

function tryFrac(text: string, i: number): Extract<DraftNode, { kind: "frac" }> | null {
  if (!cmdAt(text, i, "\\frac")) return null;
  const num = readBraceGroup(text, i + 5);
  if (!num) return null;
  const den = readBraceGroup(text, num.close + 1);
  if (!den) return null;
  return { kind: "frac", start: i, end: den.close + 1, num, den };
}

function trySqrt(text: string, i: number): Extract<DraftNode, { kind: "sqrt" }> | null {
  if (!cmdAt(text, i, "\\sqrt")) return null;
  let j = i + 5;
  let index: LatexGroup | undefined;
  if (text[j] === "[") {
    const g = readDelimGroup(text, j, "[", "]");
    if (!g) return null;
    index = g;
    j = g.close + 1;
  }
  const body = readBraceGroup(text, j);
  if (!body) return null;
  return { kind: "sqrt", start: i, end: body.close + 1, index, body };
}

function tryBinom(text: string, i: number): Extract<DraftNode, { kind: "binom" }> | null {
  if (!cmdAt(text, i, "\\binom")) return null;
  const n = readBraceGroup(text, i + 6);
  if (!n) return null;
  const k = readBraceGroup(text, n.close + 1);
  if (!k) return null;
  return { kind: "binom", start: i, end: k.close + 1, n, k };
}

function tryVec(text: string, i: number): Extract<DraftNode, { kind: "vec" }> | null {
  if (!cmdAt(text, i, "\\vec")) return null;
  const body = readBraceGroup(text, i + 4);
  if (!body) return null;
  return { kind: "vec", start: i, end: body.close + 1, body };
}

function tryScript(text: string, i: number): Extract<DraftNode, { kind: "script" }> | null {
  const mark = text[i];
  if (mark !== "^" && mark !== "_") return null;
  if (text[i - 1] === "\\") return null;
  const body = readBraceGroup(text, i + 1);
  if (!body) return null;
  return { kind: "script", start: i, end: body.close + 1, mark, body };
}

/** `{` that closes a `\command` stays with that command (`\mathrm{rad}`). */
function braceFollowsCommand(text: string, braceIndex: number): boolean {
  let j = braceIndex - 1;
  while (j >= 0 && /[A-Za-z]/.test(text[j]!)) j -= 1;
  return text[j] === "\\";
}

function tryBrace(text: string, i: number): Extract<DraftNode, { kind: "brace" }> | null {
  if (text[i] !== "{") return null;
  const prev = text[i - 1];
  if (prev === "\\" || prev === "^" || prev === "_" || prev === "}") return null;
  if (braceFollowsCommand(text, i)) return null;
  const body = readBraceGroup(text, i);
  if (!body) return null;
  return { kind: "brace", start: i, end: body.close + 1, body };
}

function tryAbs(text: string, i: number): Extract<DraftNode, { kind: "abs" }> | null {
  if (text[i] !== "|" || text[i - 1] === "\\") return null;
  const close = text.indexOf("|", i + 1);
  if (close === -1) return null;
  return { kind: "abs", start: i, end: close + 1, body: { open: i, close } };
}

function trySetBrace(text: string, i: number): Extract<DraftNode, { kind: "group" }> | null {
  const body = readSetBrace(text, i);
  if (!body) return null;
  return {
    kind: "group",
    start: i,
    end: body.close + 2,
    open: "{",
    close: "}",
    body,
  };
}

function tryGroup(text: string, i: number): Extract<DraftNode, { kind: "group" }> | null {
  const openCh = text[i];
  if ((openCh !== "(" && openCh !== "[") || text[i - 1] === "\\") return null;
  const closeCh = openCh === "(" ? ")" : "]";
  const body = readDelimGroup(text, i, openCh, closeCh);
  if (!body) return null;
  let start = i;
  if (openCh === "(" && i > 0 && /[A-Za-z]/.test(text[i - 1]!)) {
    let j = i - 1;
    while (j >= 0 && /[A-Za-z]/.test(text[j]!)) j -= 1;
    if (text[j] === "\\") start = j;
  }
  return { kind: "group", start, end: body.close + 1, open: openCh, close: closeCh, body };
}

/** Top-level tappable constructs in the composer draft (source offsets). */
export function findDraftNodes(text: string): DraftNode[] {
  const nodes: DraftNode[] = [];
  let i = 0;
  let textStart = 0;
  const flush = (end: number) => {
    if (end > textStart) nodes.push({ kind: "text", start: textStart, end });
  };
  while (i < text.length) {
    const frac = tryFrac(text, i);
    if (frac) {
      flush(i);
      nodes.push(frac);
      textStart = i = frac.end;
      continue;
    }
    const sqrt = trySqrt(text, i);
    if (sqrt) {
      flush(i);
      nodes.push(sqrt);
      textStart = i = sqrt.end;
      continue;
    }
    const script = tryScript(text, i);
    if (script) {
      flush(i);
      nodes.push(script);
      textStart = i = script.end;
      continue;
    }
    const binom = tryBinom(text, i);
    if (binom) {
      flush(i);
      nodes.push(binom);
      textStart = i = binom.end;
      continue;
    }
    const vec = tryVec(text, i);
    if (vec) {
      flush(i);
      nodes.push(vec);
      textStart = i = vec.end;
      continue;
    }
    const setBrace = trySetBrace(text, i);
    if (setBrace) {
      flush(i);
      nodes.push(setBrace);
      textStart = i = setBrace.end;
      continue;
    }
    const brace = tryBrace(text, i);
    if (brace) {
      flush(i);
      nodes.push(brace);
      textStart = i = brace.end;
      continue;
    }
    const abs = tryAbs(text, i);
    if (abs) {
      flush(i);
      nodes.push(abs);
      textStart = i = abs.end;
      continue;
    }
    const group = tryGroup(text, i);
    if (group && group.start >= textStart) {
      flush(group.start);
      nodes.push(group);
      textStart = i = group.end;
      continue;
    }
    i += 1;
  }
  flush(text.length);
  return nodes;
}

/** Caret just after an opening `$` so the next insert/delete is at the front. */
export function caretBeforeExpression(text: string): number {
  return text.startsWith("$") ? 1 : 0;
}

/** Caret just inside a trailing `$…$` pair so the next insert stays in math. */
export function caretAfterExpression(text: string): number {
  if (text.endsWith("$") && text.includes("$")) return Math.max(0, text.length - 1);
  return text.length;
}

function shiftGroup(group: LatexGroup, delta: number): LatexGroup {
  return { open: group.open + delta, close: group.close + delta };
}

/** Rebase nodes parsed from a slot's inner text onto the full draft. */
export function shiftDraftNodes(nodes: DraftNode[], delta: number): DraftNode[] {
  if (delta === 0) return nodes;
  return nodes.map((node) => {
    const start = node.start + delta;
    const end = node.end + delta;
    switch (node.kind) {
      case "text":
        return { kind: "text", start, end };
      case "frac":
        return {
          kind: "frac",
          start,
          end,
          num: shiftGroup(node.num, delta),
          den: shiftGroup(node.den, delta),
        };
      case "sqrt":
        return {
          kind: "sqrt",
          start,
          end,
          index: node.index ? shiftGroup(node.index, delta) : undefined,
          body: shiftGroup(node.body, delta),
        };
      case "script":
        return { kind: "script", start, end, mark: node.mark, body: shiftGroup(node.body, delta) };
      case "binom":
        return { kind: "binom", start, end, n: shiftGroup(node.n, delta), k: shiftGroup(node.k, delta) };
      case "group":
        return { ...node, start, end, body: shiftGroup(node.body, delta) };
      case "vec":
      case "abs":
      case "brace":
        return { ...node, start, end, body: shiftGroup(node.body, delta) };
    }
  });
}

function nodeSlots(node: Exclude<DraftNode, { kind: "text" }>): LatexGroup[] {
  if (node.kind === "frac") return [node.num, node.den];
  if (node.kind === "binom") return [node.n, node.k];
  if (node.kind === "sqrt") return node.index ? [node.index, node.body] : [node.body];
  return [node.body];
}

/** `\mathrm{rad}` and `\binom{}{}` are one key. Nested braces stay out of this. */
const COMMAND_GROUPS = /\\[A-Za-z]+(?:\{[^{}]*\})+$/;
const COMMAND_GROUPS_START = /^\\[A-Za-z]+(?:\{[^{}]*\})+/;
const SYMBOL_COMMAND = /\\[^A-Za-z\s]$/;
const SYMBOL_COMMAND_START = /^\\[^A-Za-z\s]/;

function lastTokenLength(prefix: string): number {
  const wrapped = prefix.match(COMMAND_GROUPS);
  if (wrapped) return wrapped[0].length;
  const symbol = prefix.match(SYMBOL_COMMAND);
  if (symbol) return symbol[0].length;
  const cmd = prefix.match(/\\[A-Za-z]+[ ]?$/);
  if (cmd) return cmd[0].length;
  return prefix.length > 0 ? 1 : 0;
}

function firstTokenLength(s: string): number {
  const wrapped = s.match(COMMAND_GROUPS_START);
  if (wrapped) return wrapped[0].length;
  const symbol = s.match(SYMBOL_COMMAND_START);
  if (symbol) return symbol[0].length;
  const cmd = s.match(/^\\[A-Za-z]+[ ]?/);
  if (cmd) return cmd[0].length;
  return s.length > 0 ? 1 : 0;
}

function matchingCloserOpen(text: string, closeIdx: number, min: number): number | null {
  const closeCh = text[closeIdx];
  const openCh = closeCh === "}" ? "{" : closeCh === "]" ? "[" : closeCh === ")" ? "(" : "";
  if (!openCh) return null;
  let depth = 0;
  for (let i = closeIdx; i >= min; i -= 1) {
    if (text[i] === closeCh) depth += 1;
    else if (text[i] === openCh) {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return null;
}

function plainCommandTouching(text: string, cut: number, min: number): [number, number] | null {
  const re = /\\[A-Za-z]+(?:\{[^{}]*\})+/g;
  const slice = text.slice(min);
  let match: RegExpExecArray | null;
  while ((match = re.exec(slice))) {
    const from = min + match.index;
    const to = from + match[0].length;
    if (cut > from && cut <= to) return [from, to];
  }
  return null;
}

function deleteRange(
  text: string,
  from: number,
  to: number,
): { text: string; selection: TextSelection } {
  return collapseEmptyMath(text.slice(0, from) + text.slice(to), from);
}

function deleteTokenBefore(
  text: string,
  cut: number,
  min: number,
): { text: string; selection: TextSelection } | null {
  if (cut <= min) return null;
  const command = plainCommandTouching(text, cut, min);
  if (command) return deleteRange(text, command[0], command[1]);
  const prev = text[cut - 1];
  if (prev === "{" && (text[cut] === "}" || text[cut] === "]" || text[cut] === ")")) {
    let from = cut - 1;
    if (from > min && (text[from - 1] === "^" || text[from - 1] === "_") && text[from - 2] !== "\\") {
      from -= 1;
    }
    if (from < min) return null;
    return deleteRange(text, from, cut + 1);
  }
  if (prev === "}" || prev === "]" || prev === ")") {
    const inside = text.slice(min, cut);
    // A finished `\mathrm{rad}` / `\text{cm}` / `\binom{}{}` deletes as one key.
    if (!COMMAND_GROUPS.test(inside)) {
      const open = matchingCloserOpen(text, cut - 1, min);
      if (open != null && open >= min) {
        if (open + 1 === cut - 1) {
          let from = open;
          if (
            from > min &&
            (text[from - 1] === "^" || text[from - 1] === "_") &&
            text[from - 2] !== "\\"
          ) {
            from -= 1;
          }
          const next = text.slice(0, from) + text.slice(cut);
          return collapseEmptyMath(next, from);
        }
        return deleteTokenBefore(text, cut - 1, open + 1);
      }
    }
  }
  const n = lastTokenLength(text.slice(min, cut));
  if (n === 0 || cut - n < min) return null;
  const delAt = cut - n;
  const next = text.slice(0, delAt) + text.slice(cut);
  return collapseEmptyMath(next, delAt);
}

function deleteTokenAfter(
  text: string,
  from: number,
  max: number,
): { text: string; selection: TextSelection } | null {
  if (from >= max) return null;
  const n = firstTokenLength(text.slice(from, max));
  if (n === 0 || from + n > max) return null;
  const next = text.slice(0, from) + text.slice(from + n);
  return collapseEmptyMath(next, from);
}

function addTokenStops(text: string, from: number, to: number, stops: Set<number>): void {
  let i = from;
  while (i < to) {
    if (text[i] !== "$") stops.add(i);
    const n = firstTokenLength(text.slice(i, to).replace(/^\$/, "")) || 1;
    if (text[i] === "$") {
      i += 1;
      continue;
    }
    i += n;
  }
}

/** Places you can park the caret by tapping or pressing ← →. */
function mathCaretStops(text: string): number[] {
  const stops = new Set<number>();
  stops.add(caretBeforeExpression(text));
  stops.add(caretAfterExpression(text));
  for (const node of findDraftNodes(text)) {
    if (node.kind === "text") {
      addTokenStops(text, node.start, node.end, stops);
      continue;
    }
    for (const slot of nodeSlots(node)) {
      stops.add(slot.open + 1);
      addTokenStops(text, slot.open + 1, slot.close, stops);
      stops.add(slot.close);
    }
  }
  return [...stops].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);
}

function collapseEmptyMath(
  text: string,
  caret: number,
): { text: string; selection: TextSelection } {
  // Only strip $ delimiters when the math span is truly empty (no content between pairs).
  // Don't globally remove $$ — it would corrupt $$display math$$ with content.
  const stripped = text.replace(/\$\$/g, "");
  const hasNonMathContent = stripped.trim().length > 0;
  let next = hasNonMathContent ? text : stripped;
  if (next === "$") next = "";
  const pos = Math.max(0, Math.min(caret, next.length));
  return commitBackspace({ text: next, selection: { start: pos, end: pos } });
}

function snapCaretOffRaw(text: string, pos: number): number {
  if (!text) return 0;
  const p = Math.max(0, Math.min(pos, text.length));
  const rawAt = (i: number) => {
    const c = text[i];
    return c === "\\" || c === "{" || c === "}";
  };
  if (p < text.length && rawAt(p)) {
    const prev = [...mathCaretStops(text)].reverse().find((s) => s <= p);
    if (prev != null) return prev;
  }
  if (p > 0 && rawAt(p - 1) && text[p] !== "$") {
    const prev = [...mathCaretStops(text)].reverse().find((s) => s < p);
    if (prev != null) return prev;
  }
  return p;
}

function commitBackspace(result: { text: string; selection: TextSelection }): {
  text: string;
  selection: TextSelection;
} {
  const start = snapCaretOffRaw(result.text, result.selection.start);
  return { text: result.text, selection: { start, end: start } };
}

function slotCut(text: string, slot: LatexGroup, caret: number): number {
  if (caret < text.length && text[caret] === "$") return slot.close;
  return Math.min(Math.max(caret, slot.open + 1), slot.close);
}

/**
 * Backspace that keeps templates valid: delete digits/commands, not `{` / `}`.
 * Empty boxes peel back into the previous box; an empty template is removed.
 */
export function spliceMathBackspace(
  text: string,
  selection: TextSelection,
): { text: string; selection: TextSelection } {
  const start = Math.max(0, Math.min(selection.start, text.length));
  const end = Math.max(start, Math.min(selection.end, text.length));
  if (start !== end) {
    return collapseEmptyMath(text.slice(0, start) + text.slice(end), start);
  }
  if (start === 0) return { text, selection: { start, end: start } };

  const pos =
    start === text.length && text.endsWith("$") ? start - 1 : start;
  const structures = findDraftNodes(text).filter(
    (n): n is Exclude<DraftNode, { kind: "text" }> => n.kind !== "text",
  );
  const node = structures.find((n) => pos > n.start && pos <= n.end);

  if (node) {
    const slots = nodeSlots(node);
    const inner = slots.filter(
      (s) => caretInGroup(pos, s) || (text[pos] === "$" && caretInGroup(pos - 1, s)),
    );
    const slot =
      (inner.length > 0
        ? inner.reduce((best, s) => (s.close - s.open < best.close - best.open ? s : best))
        : slots.filter((s) => s.close < pos).at(-1)) ?? slots.at(-1);
    if (!slot) {
      return commitBackspace(
        deleteTokenBefore(text, pos, 0) ?? { text, selection: { start: pos, end: pos } },
      );
    }

    if (slot.close - slot.open > 1) {
      const cut = slotCut(text, slot, pos);
      const deleted = deleteTokenBefore(text, cut, slot.open + 1);
      if (deleted) return deleted;
      const forward = deleteTokenAfter(text, slot.open + 1, slot.close);
      if (forward) return forward;
    }

    for (let i = slots.indexOf(slot) - 1; i >= 0; i -= 1) {
      const prev = slots[i]!;
      if (prev.close - prev.open > 1) {
        const deleted = deleteTokenBefore(text, prev.close, prev.open + 1);
        if (deleted) return deleted;
      }
    }

    const next = text.slice(0, node.start) + text.slice(node.end);
    return collapseEmptyMath(next, node.start);
  }

  let cut = pos;
  if (text[cut] === "$") {
    /* delete the token before the closing $, never the dollar itself */
  } else if (cut === text.length && text[cut - 1] === "$") {
    cut -= 1;
  }
  const prefix = text.slice(0, cut);
  const n = lastTokenLength(prefix);
  const piece = n > 0 ? prefix.slice(-n) : "";
  if (/^[{}()[\]|]$/.test(piece)) {
    const ended = structures.filter((s) => s.end <= cut).at(-1);
    if (ended) {
      const last = nodeSlots(ended).at(-1);
      if (last && last.close - last.open > 1) {
        const deleted = deleteTokenBefore(text, last.close, last.open + 1);
        if (deleted) return deleted;
      }
      return collapseEmptyMath(text.slice(0, ended.start) + text.slice(ended.end), ended.start);
    }
  }
  if (piece === "$" || pos <= caretBeforeExpression(text)) {
    const first = structures.find((n) => n.start >= pos) ?? structures[0];
    if (first) {
      const slot = nodeSlots(first)[0];
      if (slot && slot.close - slot.open > 1) {
        const forward = deleteTokenAfter(text, slot.open + 1, slot.close);
        if (forward) return forward;
      }
      return collapseEmptyMath(text.slice(0, first.start) + text.slice(first.end), first.start);
    }
    const innerStart = caretBeforeExpression(text);
    const innerEnd = caretAfterExpression(text);
    const forward = deleteTokenAfter(text, Math.min(innerStart, innerEnd), innerEnd);
    if (forward) return forward;
    return collapseEmptyMath("", 0);
  }
  return commitBackspace(
    deleteTokenBefore(text, cut, 0) ?? { text, selection: { start: pos, end: pos } },
  );
}
