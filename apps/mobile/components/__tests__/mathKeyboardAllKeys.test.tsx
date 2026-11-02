import { act, type ReactElement } from "react";
import { createRoot, type JsonNode } from "test-renderer";

import { MathDraftPreview } from "@/features/chat/components/MathDraftPreview";
import { MathKeyboardBar } from "@/features/chat/components/MathKeyboardBar";
import { MATH_KEYBOARD_GROUPS, MATH_KEYBOARD_SYMBOLS, autoAdvanceNextEmptySlot, caretStepRight, spliceMathInsert, tapAdvancesToNextSlot, type MathKeyboardSymbol } from "@/lib/math/keyboardSymbols";
import { MATH_PAD_KEYS } from "@/lib/math/keyboardCatalog";
import { spliceMathBackspace } from "@/lib/math/draftSlots";
import { appendConverterDigit, CONVERTER_DEFAULT_DIGITS } from "@/features/chat/model/unitConverter";

// A command glued to its argument (`mathbbN`, `mathrmi`) is a leak too: no trailing \b.
const RAW = /[\\{}]|\b(?:binom|mathrm|mathbb|mathbf|tfrac|dfrac|frac|sqrt|partial|nabla|infty|cdot|oint)/;

function press(text: string, caret: number, spec: MathKeyboardSymbol) {
  const jump = tapAdvancesToNextSlot(text, caret, spec.id);
  if (jump != null) return { text, caret: jump };
  const result = spliceMathInsert(text, { start: caret, end: caret }, spec);
  const advanced = autoAdvanceNextEmptySlot(text, caret, result.text, result.selection.start, spec);
  return { text: result.text, caret: advanced ?? result.selection.start };
}

/** Key ids, or `→` to step right, typed from an empty composer. */
function typeKeys(keys: string[]): string {
  let state = { text: "", caret: 0 };
  for (const id of keys) {
    if (id === "→") {
      state = { text: state.text, caret: caretStepRight(state.text, state.caret) };
      continue;
    }
    state = press(state.text, state.caret, SPECS.find((spec) => spec.id === id)!);
  }
  return state.text;
}

function del(text: string, caret: number) {
  const result = spliceMathBackspace(text, { start: caret, end: caret });
  return { text: result.text, caret: result.selection.start };
}

const root = createRoot({
  textComponentTypes: ["Text", "RCTText"],
  publicTextComponentTypes: ["Text"],
});

function collect(node: JsonNode | JsonNode[] | null): string[] {
  if (node == null) return [];
  if (typeof node === "string") return [node];
  if (Array.isArray(node)) return node.flatMap(collect);
  return (node.children ?? []).flatMap((child) => collect(child));
}

function paint(element: ReactElement) {
  act(() => {
    root.render(element);
  });
  return root.container.toJSON();
}

function pressTestId(testID: string) {
  const matches = root.container.queryAll((node) => node.props.testID === testID);
  if (matches.length === 0) throw new Error(`missing ${testID}`);
  let fiber = matches[0]!.unstable_fiber;
  while (fiber) {
    const onPress = fiber.memoizedProps?.onPress as ((event?: object) => void) | undefined;
    if (typeof onPress === "function") {
      act(() => {
        onPress({ nativeEvent: {} });
      });
      return;
    }
    fiber = fiber.return;
  }
  throw new Error(`no press handler for ${testID}`);
}

function previewTree(input: string, caret: number): JsonNode | JsonNode[] | null {
  if (!input) return null;
  return paint(<MathDraftPreview input={input} caret={caret} showCaret={false} />);
}

function visible(input: string, caret: number): string {
  return collect(previewTree(input, caret)).join("");
}

function previewIds(input: string, caret: number): string[] {
  const ids: string[] = [];
  const walk = (node: JsonNode | JsonNode[] | string | null | undefined) => {
    if (node == null || typeof node === "string") return;
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    const id = node.props?.testID;
    if (typeof id === "string") ids.push(id);
    (node.children ?? []).forEach((child) => walk(child));
  };
  walk(previewTree(input, caret));
  return ids;
}

function leaks(shown: string, id = ""): boolean {
  if (id === "braces" || id.startsWith("braces+")) {
    return /\\/.test(shown);
  }
  return RAW.test(shown);
}

type Issue = { id: string; step: string; source: string; shown: string };

async function walkDeletes(id: string, startText: string, startCaret: number, issues: Issue[]) {
  let text = startText;
  let caret = startCaret;
  const seen = new Set<string>();
  for (let i = 0; i < 48; i += 1) {
    const key = `${caret}:${text}`;
    if (seen.has(key)) {
      issues.push({
        id,
        step: `stuck after ${i} deletes`,
        source: text,
        shown: await visible(text, caret),
      });
      return;
    }
    seen.add(key);
    const shown = await visible(text, caret);
    if (leaks(shown, id)) {
      issues.push({ id, step: `delete ${i}`, source: text, shown });
    }
    if (!text) return;
    const next = del(text, caret);
    if (next.text === text && next.caret === caret) {
      issues.push({ id, step: `delete no-op at ${caret}`, source: text, shown });
      return;
    }
    text = next.text;
    caret = next.caret;
  }
  if (text) {
    issues.push({ id, step: "never emptied", source: text, shown: await visible(text, caret) });
  }
}

const SPECS: MathKeyboardSymbol[] = [...MATH_KEYBOARD_SYMBOLS, ...MATH_PAD_KEYS];

function shapeIssue(id: string, source: string, shown: string, ids: string[]): string | null {
  if (id === "fact" && (shown !== "n!" || source.includes("{"))) return "factorial shows a brace slot";
  if (id === "binom" && (!shown.startsWith("C(") || !ids.includes("math-slot-binom-n"))) {
    return "binomial is not two slots";
  }
  if (id === "vec" && (!shown.includes("→") || !ids.includes("math-slot-vec"))) {
    return "vector slot is blank";
  }
  if (id === "ddv" && !ids.includes("math-slot-brace")) return "derivative has no variable slot";
  return null;
}

describe("math keyboard keys", () => {
  afterAll(() => {
    act(() => {
      root.unmount();
    });
  });

  it("presses every key, then deletes without showing raw latex", async () => {
    const issues: Issue[] = [];
    for (const spec of SPECS) {
      const inserted = press("", 0, spec);
      const shown = await visible(inserted.text, inserted.caret);
      const ids = previewIds(inserted.text, inserted.caret);
      const shape = shapeIssue(spec.id, inserted.text, shown, ids);
      if (shape) {
        issues.push({ id: spec.id, step: shape, source: inserted.text, shown });
      }
      if (leaks(shown, spec.id)) {
        issues.push({ id: spec.id, step: "insert", source: inserted.text, shown });
      }
      await walkDeletes(spec.id, inserted.text, inserted.caret, issues);

      // Fill empty boxes with a digit, the way the number pad does, then delete.
      let filled = inserted;
      for (let n = 0; n < 3; n += 1) {
        const digit = MATH_PAD_KEYS.find((k) => k.id === `digit-${n + 1}`)!;
        const next = press(filled.text, filled.caret, digit);
        if (next.text === filled.text && next.caret === filled.caret) break;
        filled = next;
      }
      if (filled.text !== inserted.text) {
        const filledShown = await visible(filled.text, filled.caret);
        if (leaks(filledShown, spec.id)) {
          issues.push({ id: spec.id, step: "filled", source: filled.text, shown: filledShown });
        }
        await walkDeletes(`${spec.id}+digits`, filled.text, filled.caret, issues);
      }
    }
    if (issues.length > 0) {
      const lines = issues
        .slice(0, 30)
        .map((issue) => `${issue.id} | ${issue.step} | shown=${issue.shown} | src=${issue.source}`);
      throw new Error(`${issues.length} issues\n${lines.join("\n")}`);
    }
  });

  it("deletes a mixed expression from the end without leaking braces", async () => {
    const sequence = ["frac", "digit-8", "frac", "digit-2", "times", "sqrt", "digit-9", "sup", "digit-2"];
    let text = "";
    let caret = 0;
    for (const id of sequence) {
      const spec = SPECS.find((s) => s.id === id)!;
      const next = press(text, caret, spec);
      text = next.text;
      caret = next.caret;
      expect(leaks(await visible(text, caret))).toBe(false);
    }
    const issues: Issue[] = [];
    await walkDeletes("mixed", text, caret, issues);
    expect(issues).toEqual([]);
    expect(text).not.toBe("");
  });

  it("renders every tab and fires every key", () => {
    const inserted: string[] = [];
    const bar = (group: (typeof MATH_KEYBOARD_GROUPS)[number]) => (
      <MathKeyboardBar
        open
        height={320}
        onToggle={() => inserted.push("abc")}
        onInsert={(spec) => inserted.push(spec.id)}
        onCaret={(direction) => inserted.push(direction)}
        onAsk={() => inserted.push("ask")}
        onStop={() => inserted.push("stop")}
        streaming={false}
        onBackspace={() => inserted.push("backspace")}
        onPaste={() => inserted.push("paste")}
        group={group}
        onGroupChange={() => undefined}
      />
    );
    paint(bar("basics"));
    pressTestId("math-keyboard-paste");
    pressTestId("math-keyboard-abc");
    const seen = new Set<string>();
    for (const group of MATH_KEYBOARD_GROUPS) {
      paint(bar(group));
      pressTestId(`math-keyboard-tab-${group}`);
      if (group === "converter") {
        for (const id of ["7", "8", "9", "AC", "4", "5", "6", "back", "1", "2", "3", "±", "0", "dot"]) {
          pressTestId(`math-converter-${id}`);
        }
        pressTestId("math-converter-ask");
        pressTestId("math-converter-swap");
        continue;
      }
      const ids = new Set<string>();
      for (const spec of SPECS) {
        const matches = root.container.queryAll((node) => node.props.testID === `math-key-${spec.id}`);
        if (matches.length === 0) continue;
        pressTestId(`math-key-${spec.id}`);
        ids.add(spec.id);
        seen.add(spec.id);
      }
      pressTestId("math-key-backspace");
      pressTestId("math-key-left");
      pressTestId("math-key-right");
      expect(ids.size).toBe(33);
    }
    expect(inserted).toContain("paste");
    expect(inserted).toContain("backspace");
    expect(inserted).toContain("left");
    expect(inserted).toContain("right");
    expect(inserted).toContain("frac");
    expect(inserted).toContain("sin");
    expect(inserted).toContain("int");
    expect(inserted).toContain("alpha");
    const missing = SPECS.map((spec) => spec.id).filter((id) => !seen.has(id));
    expect(missing).toEqual([]);
  });

  it.each([
    ["2(x+3)", ["digit-2", "parens", "var-x", "plus", "digit-3"], "$2(x+3)$"],
    ["(x+1)(x−1)", ["parens", "var-x", "plus", "digit-1", "→", "parens", "var-x", "minus", "digit-1"], "$(x+1)(x-1)$"],
    ["√(x+1)", ["sqrt", "var-x", "plus", "digit-1"], "$\\sqrt{x+1}$"],
    ["x^(y+1)", ["sup", "var-y", "plus", "digit-1"], "$x^{y+1}$"],
    ["|x−3|", ["abs", "var-x", "minus", "digit-3"], "$|x-3|$"],
    ["sin(x+π) + 1", ["sin", "var-x", "plus", "pi", "→", "plus", "digit-1"], "$\\sin(x+\\pi )+1$"],
    ["x² y", ["sq", "var-y"], "$x^{2}y$"],
    ["x^n then y", ["sup", "var-x", "→", "var-y"], "$x^{x}y$"],
    ["∫ from 0 to 1", ["dint", "digit-0", "dint", "digit-1"], "$\\int_{0}^{1}$"],
    ["∫ bounds by →", ["dint", "digit-0", "→", "digit-1", "→", "var-x"], "$\\int_{0}^{1}x$"],
    ["∑ n=1 to 5", ["sum", "var-y", "eq", "digit-1", "sum", "digit-5"], "$\\sum_{y=1}^{5}$"],
    ["nCr 5 2", ["binom", "digit-5", "binom", "digit-2"], "$\\binom{5}{2}$"],
    ["lim x→0 of x", ["lim", "var-x", "to", "digit-0", "→", "var-x"], "$\\lim_{x\\to 0}x$"],
    ["1/2 + 1", ["frac", "digit-1", "frac", "digit-2", "→", "plus", "digit-1"], "$\\frac{1}{2}+1$"],
  ])("types %s with the keys", (_name, keys, expected) => {
    expect(typeKeys(keys)).toBe(expected);
  });

  it("types every converter key", () => {
    let digits = CONVERTER_DEFAULT_DIGITS;
    let fresh = true;
    for (const key of ["AC", "7", "8", ".", "5", "back", "±", "0", "±"]) {
      digits = appendConverterDigit(digits, key, fresh);
      fresh = key === "AC" || (key === "back" && digits === CONVERTER_DEFAULT_DIGITS);
      expect(digits).not.toMatch(/[\\{}]/);
    }
  });
});
