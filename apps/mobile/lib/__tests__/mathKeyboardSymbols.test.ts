import { autoAdvanceNextEmptySlot, caretInGroup, caretStepLeft, caretStepRight, MATH_KEYBOARD_GROUPS, MATH_KEYBOARD_SYMBOLS, padRows, spliceMathInsert, symbolA11yLabel, tapAdvancesToNextSlot, type SymbolPage } from "@/lib/math/keyboardSymbols";
import { findFracSlots, findLognSlots, findNrootSlots } from "@/lib/math/keyboardSlots";
import { isCursorInsideInlineMath, MATH_PAD_KEYS, SYMBOL_A11Y } from "@/lib/math/keyboardCatalog";
import { PAD_ROWS } from "@/lib/math/keyboardPages";

const SYMBOL_PAGES = MATH_KEYBOARD_GROUPS.filter((group): group is SymbolPage => group !== "converter");
const pageKeyIds = (page: SymbolPage) =>
  padRows(page).flatMap((row) => row.flatMap((cell) => (cell.kind === "insert" ? [cell.spec.id] : [])));

describe("spliceMathInsert", () => {
  it("wraps a snippet in $...$ when the caret is outside math", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    const result = spliceMathInsert("ab", { start: 1, end: 1 }, frac);
    expect(result.text).toBe("a$\\frac{}{}$b");
    expect(result.selection).toEqual({ start: 8, end: 8 });
  });

  it("does not add a second $ pair inside an open math span", () => {
    const sqrt = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "sqrt")!;
    const result = spliceMathInsert("$x+$", { start: 3, end: 3 }, sqrt);
    expect(result.text).toBe("$x+\\sqrt{}$");
    expect(isCursorInsideInlineMath("$x+$", 3)).toBe(true);
    expect(result.selection.start).toBe(9);
  });

  it("replaces the current selection", () => {
    const pi = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "pi")!;
    const result = spliceMathInsert("foo", { start: 0, end: 3 }, pi);
    expect(result.text).toBe("$\\pi $");
  });

  it("places a following digit in the numerator, then the denominator after jumping slots", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    const one = { id: "digit-1", label: "1", insert: "1", cursorOffset: 1, group: "pad" as const };
    const two = { id: "digit-2", label: "2", insert: "2", cursorOffset: 1, group: "pad" as const };
    const afterFrac = spliceMathInsert("", { start: 0, end: 0 }, frac);
    expect(afterFrac.text).toBe("$\\frac{}{}$");
    const slots = findFracSlots(afterFrac.text);
    expect(caretInGroup(afterFrac.selection.start, slots[0]!.num)).toBe(true);
    const afterNum = spliceMathInsert(afterFrac.text, afterFrac.selection, one);
    expect(afterNum.text).toBe("$\\frac{1}{}$");
    const denAfterNum = findFracSlots(afterNum.text)[0]!.den;
    const afterDen = spliceMathInsert(afterNum.text, { start: denAfterNum.close, end: denAfterNum.close }, two);
    expect(afterDen.text).toBe("$\\frac{1}{2}$");
  });

  it("keeps every symbol cursor inside the insert snippet", () => {
    for (const spec of MATH_KEYBOARD_SYMBOLS) {
      expect(spec.cursorOffset).toBeGreaterThanOrEqual(0);
      expect(spec.cursorOffset).toBeLessThanOrEqual(spec.insert.length);
    }
  });

  it("ⁿ√ inserts an nth-root index, not n times square root", () => {
    const nroot = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "nroot")!;
    expect(nroot.insert).toBe("\\sqrt[]{}");
    expect(spliceMathInsert("", { start: 0, end: 0 }, nroot).text).toBe("$\\sqrt[]{}$");
  });

  it("f′ attaches to a base, or leaves the caret in front of the prime", () => {
    const prime = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "prime")!;
    expect(spliceMathInsert("$x$", { start: 2, end: 2 }, prime).text).toBe("$x'$");
    expect(spliceMathInsert("", { start: 0, end: 0 }, prime).text).toBe("$^{\\prime}$");
    expect(MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "partial-x")?.group).toBe("calc");
  });

  it("n! attaches to a number, or selects the n so the next digit replaces it", () => {
    const fact = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "fact")!;
    const empty = spliceMathInsert("", { start: 0, end: 0 }, fact);
    expect(empty.text).toBe("$n!$");
    expect(empty.selection).toEqual({ start: 1, end: 2 });
    const five = spliceMathInsert(empty.text, empty.selection, {
      id: "digit-5",
      label: "5",
      insert: "5",
      cursorOffset: 1,
      group: "pad",
    });
    expect(five.text).toBe("$5!$");
    expect(spliceMathInsert("$5$", { start: 2, end: 2 }, fact).text).toBe("$5!$");
  });

  it("x² inserts a squared x, or attaches ^{2} to an existing base", () => {
    const sq = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "sq")!;
    expect(spliceMathInsert("", { start: 0, end: 0 }, sq).text).toBe("$x^{2}$");
    expect(spliceMathInsert("$3$", { start: 2, end: 2 }, sq).text).toBe("$3^{2}$");
  });

  it("xⁿ inserts a base x and an exponent box, or attaches ^ to an existing base", () => {
    const sup = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "sup")!;
    expect(spliceMathInsert("", { start: 0, end: 0 }, sup).text).toBe("$x^{}$");
    expect(spliceMathInsert("$2$", { start: 2, end: 2 }, sup).text).toBe("$2^{}$");
    expect(spliceMathInsert("$x$", { start: 2, end: 2 }, sup).text).toBe("$x^{}$");
  });

  it("eⁿ inserts Euler's number with an exponent box", () => {
    const euler = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "euler")!;
    const result = spliceMathInsert("", { start: 0, end: 0 }, euler);
    expect(result.text).toBe("$e^{}$");
    expect(result.text[result.selection.start]).toBe("}");
  });

  it("d/d□ lands in the variable slot", () => {
    const ddv = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "ddv")!;
    const result = spliceMathInsert("", { start: 0, end: 0 }, ddv);
    expect(result.text).toBe("$\\frac{d}{d{}}$");
    expect(result.text.slice(result.selection.start - 1, result.selection.start + 1)).toBe("{}");
  });

  it("° attaches to a number, or inserts a base box on an empty draft", () => {
    const deg = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "deg")!;
    const empty = spliceMathInsert("", { start: 0, end: 0 }, deg);
    expect(empty.text).toBe("$^{\\circ}$");
    expect(empty.text[empty.selection.start]).toBe("^");
    const typed = spliceMathInsert(empty.text, empty.selection, {
      id: "digit-3",
      label: "3",
      insert: "3",
      cursorOffset: 1,
      group: "pad" as const,
    });
    expect(typed.text).toBe("$3^{\\circ}$");
    expect(spliceMathInsert("$30$", { start: 3, end: 3 }, deg).text).toBe("$30^{\\circ}$");
  });

  it("labels second derivative as d²/dx², with drawn superscripts", () => {
    expect(MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "der2")?.label).toBe("d^{2}/dx^{2}");
  });

  it("digits stay prose inside a convert draft", () => {
    const one = { id: "digit-1", label: "1", insert: "1", cursorOffset: 1, group: "pad" as const };
    const typed = spliceMathInsert("convert  km to mi", { start: 8, end: 8 }, one);
    expect(typed.text).toBe("convert 1 km to mi");
    expect(typed.text).not.toContain("$");
  });
});

describe("key insert matches the button", () => {
  it.each([
    ["frac", "\\frac{}{}"],
    ["sqrt", "\\sqrt{}"],
    ["nroot", "\\sqrt[]{}"],
    ["sup", "x^{}"],
    ["sub", "x_{}"],
    ["abs", "||"],
    ["pi", "\\pi "],
    ["leq", "\\leq "],
    ["geq", "\\geq "],
    ["neq", "\\neq "],
    ["lt", "<"],
    ["gt", ">"],
    ["times", "\\times "],
    ["div", "\\div "],
    ["plus", "+"],
    ["minus", "-"],
    ["eq", "="],
    ["parens", "()"],
    ["brackets", "[]"],
    ["braces", "\\{\\}"],
    ["sq", "x^{2}"],
    ["angle", "\\angle "],
    ["sin", "\\sin()"],
    ["cos", "\\cos()"],
    ["tan", "\\tan()"],
    ["cot", "\\cot()"],
    ["sec", "\\sec()"],
    ["csc", "\\csc()"],
    ["arcsin", "\\arcsin()"],
    ["arccos", "\\arccos()"],
    ["arctan", "\\arctan()"],
    ["arccot", "\\cot^{-1}()"],
    ["arcsec", "\\sec^{-1}()"],
    ["arccsc", "\\csc^{-1}()"],
    ["rad", "\\mathrm{rad}"],
    ["arcsinh", "\\sinh^{-1}()"],
    ["arccosh", "\\cosh^{-1}()"],
    ["arctanh", "\\tanh^{-1}()"],
    ["log", "\\log()"],
    ["ln", "\\ln()"],
    ["logn", "\\log_{}()"],
    ["exp", "\\exp()"],
    ["tenpow", "10^{}"],
    ["sinh", "\\sinh()"],
    ["cosh", "\\cosh()"],
    ["tanh", "\\tanh()"],
    ["deg", "^{\\circ}"],
    ["int", "\\int "],
    ["dint", "\\int_{}^{}"],
    ["iint", "\\iint "],
    ["sum", "\\sum_{}^{}"],
    ["prod", "\\prod_{}^{}"],
    ["lim", "\\lim_{}"],
    ["infty", "\\infty "],
    ["partial", "\\partial "],
    ["der", "\\frac{d}{dx}"],
    ["der2", "\\frac{d^{2}}{dx^{2}}"],
    ["to", "\\to "],
    ["dx", "\\,dx"],
    ["pm", "\\pm "],
    ["approx", "\\approx "],
    ["binom", "\\binom{}{}"],
    ["percent", "\\%"],
    ["euler", "e^{}"],
    ["imag", "\\mathrm{i}"],
    ["oint", "\\oint "],
    ["iiint", "\\iiint "],
    ["nabla", "\\nabla "],
    ["vec", "\\vec{}"],
    ["cdot", "\\cdot "],
    ["ddv", "\\frac{d}{d{}}"],
    ["alpha", "\\alpha "],
    ["beta", "\\beta "],
    ["gamma", "\\gamma "],
    ["delta", "\\delta "],
    ["epsilon", "\\varepsilon "],
    ["zeta", "\\zeta "],
    ["eta", "\\eta "],
    ["theta", "\\theta "],
    ["kappa", "\\kappa "],
    ["lambda", "\\lambda "],
    ["mu", "\\mu "],
    ["nu", "\\nu "],
    ["xi", "\\xi "],
    ["rho", "\\rho "],
    ["sigma", "\\sigma "],
    ["tau", "\\tau "],
    ["phi", "\\phi "],
    ["chi", "\\chi "],
    ["psi", "\\psi "],
    ["omega", "\\omega "],
    ["Gamma", "\\Gamma "],
    ["Delta", "\\Delta "],
    ["Sigma", "\\Sigma "],
    ["Omega", "\\Omega "],
  ] as const)("%s inserts %s", (id, insert) => {
    const spec = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === id);
    expect(spec?.insert).toBe(insert);
  });
});

describe("slot navigation", () => {
  it("advances from a filled numerator to an empty denominator", () => {
    const text = "$\\frac{1}{}$";
    const slots = findFracSlots(text);
    expect(caretStepRight(text, slots[0]!.num.close)).toBe(slots[0]!.den.open + 1);
    expect(tapAdvancesToNextSlot(text, slots[0]!.num.close, "frac")).toBe(slots[0]!.den.close);
  });

  it("auto-advances after inserting pi into an empty numerator", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    const pi = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "pi")!;
    const afterFrac = spliceMathInsert("", { start: 0, end: 0 }, frac);
    const afterPi = spliceMathInsert(afterFrac.text, afterFrac.selection, pi);
    const jump = autoAdvanceNextEmptySlot(
      afterFrac.text,
      afterFrac.selection.start,
      afterPi.text,
      afterPi.selection.start,
      pi,
    );
    expect(jump).not.toBeNull();
    expect(caretInGroup(jump!, findFracSlots(afterPi.text)[0]!.den)).toBe(true);
  });

  it("does not auto-advance after a digit so multi-digit numerators stay possible", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    const one = { id: "digit-1", label: "1", insert: "1", cursorOffset: 1, group: "pad" as const };
    const afterFrac = spliceMathInsert("", { start: 0, end: 0 }, frac);
    const afterOne = spliceMathInsert(afterFrac.text, afterFrac.selection, one);
    expect(
      autoAdvanceNextEmptySlot(
        afterFrac.text,
        afterFrac.selection.start,
        afterOne.text,
        afterOne.selection.start,
        one,
      ),
    ).toBeNull();
  });

  it("second fraction tap jumps to an empty denominator instead of nesting", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    const one = { id: "digit-1", label: "1", insert: "1", cursorOffset: 1, group: "pad" as const };
    const afterFrac = spliceMathInsert("", { start: 0, end: 0 }, frac);
    const afterOne = spliceMathInsert(afterFrac.text, afterFrac.selection, one);
    const jump = tapAdvancesToNextSlot(afterOne.text, afterOne.selection.start, "frac");
    expect(jump).toBe(findFracSlots(afterOne.text)[0]!.den.close);
  });

  it("→ leaves a filled last box instead of wrapping back to the first", () => {
    const text = "$\\frac{8}{8}$";
    const slots = findFracSlots(text);
    expect(caretStepRight(text, slots[0]!.den.close)).toBe(slots[0]!.den.close + 1);
  });

  it("keeps commas inside parentheses, brackets, and set braces", () => {
    const comma = MATH_PAD_KEYS.find((s) => s.id === "comma")!;
    const one = MATH_PAD_KEYS.find((s) => s.id === "digit-1")!;
    const two = MATH_PAD_KEYS.find((s) => s.id === "digit-2")!;
    const expected: Record<string, string> = {
      parens: "$(1,2)$",
      brackets: "$[1,2]$",
      braces: "$\\{1,2\\}$",
    };
    for (const id of ["parens", "brackets", "braces"] as const) {
      const spec = MATH_KEYBOARD_SYMBOLS.find((item) => item.id === id)!;
      const opened = spliceMathInsert("", { start: 0, end: 0 }, spec);
      const first = spliceMathInsert(opened.text, opened.selection, one);
      const withComma = spliceMathInsert(first.text, first.selection, comma);
      const second = spliceMathInsert(withComma.text, withComma.selection, two);
      expect(second.text).toBe(expected[id]);
    }
  });

  it("types × into the denominator, and after the fraction once → leaves it", () => {
    const times = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "times")!;
    const text = "$\\frac{8}{8}$";
    const den = findFracSlots(text)[0]!.den;
    const inside = spliceMathInsert(text, { start: den.close, end: den.close }, times);
    expect(inside.text).toBe("$\\frac{8}{8\\times }$");
    const after = caretStepRight(text, den.close);
    expect(spliceMathInsert(text, { start: after, end: after }, times).text).toBe(
      "$\\frac{8}{8}\\times $",
    );
  });

  it("auto-advances from a filled nth-root index into the radicand", () => {
    const nroot = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "nroot")!;
    const pi = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "pi")!;
    const afterRoot = spliceMathInsert("", { start: 0, end: 0 }, nroot);
    expect(caretInGroup(afterRoot.selection.start, findNrootSlots(afterRoot.text)[0]!.index)).toBe(
      true,
    );
    const afterPi = spliceMathInsert(afterRoot.text, afterRoot.selection, pi);
    const jump = autoAdvanceNextEmptySlot(
      afterRoot.text,
      afterRoot.selection.start,
      afterPi.text,
      afterPi.selection.start,
      pi,
    );
    expect(jump).not.toBeNull();
    expect(caretInGroup(jump!, findNrootSlots(afterPi.text)[0]!.radicand)).toBe(true);
  });

  it("does not auto-advance an nth-root index after a digit", () => {
    const nroot = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "nroot")!;
    const three = { id: "digit-3", label: "3", insert: "3", cursorOffset: 1, group: "pad" as const };
    const afterRoot = spliceMathInsert("", { start: 0, end: 0 }, nroot);
    const afterThree = spliceMathInsert(afterRoot.text, afterRoot.selection, three);
    expect(
      autoAdvanceNextEmptySlot(
        afterRoot.text,
        afterRoot.selection.start,
        afterThree.text,
        afterThree.selection.start,
        three,
      ),
    ).toBeNull();
    expect(
      tapAdvancesToNextSlot(afterThree.text, afterThree.selection.start, "nroot"),
    ).toBe(findNrootSlots(afterThree.text)[0]!.radicand.close);
  });

  it("auto-advances from a filled logₙ base into the argument", () => {
    const logn = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "logn")!;
    const pi = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "pi")!;
    const afterLog = spliceMathInsert("", { start: 0, end: 0 }, logn);
    expect(caretInGroup(afterLog.selection.start, findLognSlots(afterLog.text)[0]!.base)).toBe(
      true,
    );
    const afterPi = spliceMathInsert(afterLog.text, afterLog.selection, pi);
    const jump = autoAdvanceNextEmptySlot(
      afterLog.text,
      afterLog.selection.start,
      afterPi.text,
      afterPi.selection.start,
      pi,
    );
    expect(jump).not.toBeNull();
    expect(caretInGroup(jump!, findLognSlots(afterPi.text)[0]!.arg)).toBe(true);
  });

  it("second logₙ tap jumps from a filled base into the empty argument", () => {
    const logn = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "logn")!;
    const two = { id: "digit-2", label: "2", insert: "2", cursorOffset: 1, group: "pad" as const };
    const afterLog = spliceMathInsert("", { start: 0, end: 0 }, logn);
    const afterTwo = spliceMathInsert(afterLog.text, afterLog.selection, two);
    expect(tapAdvancesToNextSlot(afterTwo.text, afterTwo.selection.start, "logn")).toBe(
      findLognSlots(afterTwo.text)[0]!.arg.close,
    );
  });
});

describe("keyboard pages", () => {
  it("lays every page out as the same 6 × 6 grid ending in ← → ⌫", () => {
    expect(SYMBOL_PAGES).toEqual(["basics", "symbols", "trig", "calc", "greek"]);
    for (const page of SYMBOL_PAGES) {
      const rows = padRows(page);
      expect(rows).toHaveLength(PAD_ROWS);
      expect(rows.every((row) => row.length === 6)).toBe(true);
      expect(rows[PAD_ROWS - 1]!.slice(-3).map((cell) => cell.kind)).toEqual([
        "left",
        "right",
        "backspace",
      ]);
    }
    expect(MATH_KEYBOARD_GROUPS).toEqual([...SYMBOL_PAGES, "converter"]);
  });

  it("puts digits, the four operations, x and = together on Basics", () => {
    const basics = pageKeyIds("basics");
    for (const id of [
      "digit-0", "digit-1", "digit-2", "digit-3", "digit-4", "digit-5", "digit-6", "digit-7",
      "digit-8", "digit-9", "digit-dot", "plus", "minus", "times", "div", "eq", "var-x",
      "parens", "frac", "sqrt", "sq",
    ]) {
      expect(basics).toContain(id);
    }
  });

  it("puts every key on a page, and only π and θ on two", () => {
    const placed = SYMBOL_PAGES.flatMap((page) => pageKeyIds(page));
    const all = [...MATH_KEYBOARD_SYMBOLS, ...MATH_PAD_KEYS].map((spec) => spec.id);
    expect(all.filter((id) => !placed.includes(id))).toEqual([]);
    const twice = [...new Set(placed.filter((id, i) => placed.indexOf(id) !== i))].sort();
    expect(twice).toEqual(["pi", "theta"]);
  });

  it("adds the keys the review found missing", () => {
    const placed = SYMBOL_PAGES.flatMap((page) => pageKeyIds(page));
    for (const id of [
      "perm", "e-const", "ratio", "in", "notin", "cup", "cap", "subset", "emptyset", "perp",
      "parallel", "cong", "sim", "triangle", "floor", "mod", "Pi", "Lambda", "Psi", "Xi",
    ]) {
      expect(placed).toContain(id);
    }
  });
});

describe("symbolA11yLabel (KB-005)", () => {
  it("returns a descriptive label for known symbol IDs", () => {
    const frac = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "frac")!;
    expect(symbolA11yLabel(frac)).toBe("Fraction");
    const sqrt = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "sqrt")!;
    expect(symbolA11yLabel(sqrt)).toBe("Square root");
    const leq = MATH_KEYBOARD_SYMBOLS.find((s) => s.id === "leq")!;
    expect(symbolA11yLabel(leq)).toBe("Less than or equal");
  });

  it("falls back to the visual label for unknown IDs", () => {
    const fake = { id: "custom", label: "★", insert: "★", cursorOffset: 1, group: "basics" as const };
    expect(symbolA11yLabel(fake)).toBe("★");
  });

  it("names every key, so a screen reader never reads the face's markup", () => {
    const missing = [...MATH_KEYBOARD_SYMBOLS, ...MATH_PAD_KEYS]
      .map((spec) => spec.id)
      .filter((id) => !SYMBOL_A11Y[id]);
    expect(missing).toEqual([]);
  });
});

describe("← and →", () => {
  it("moves numerator → denominator → after the fraction, and back", () => {
    const text = "$\\frac{1}{2}$";
    const slots = findFracSlots(text)[0]!;
    const den = caretStepRight(text, slots.num.close);
    expect(den).toBe(slots.den.open + 1);
    expect(caretStepLeft(text, den)).toBe(slots.num.close);
    const end = caretStepRight(text, slots.den.close);
    expect(end).toBe(text.length - 1);
    expect(caretStepRight(text, end)).toBe(end);
  });

  it("reaches both bounds of a definite integral", () => {
    const text = "$\\int_{0}^{}$";
    const lower = text.indexOf("{0}") + 2;
    const upper = caretStepRight(text, lower);
    expect(text.slice(upper - 2, upper + 1)).toBe("^{}");
  });

  it("steps over a symbol and \\mathbb{R} whole", () => {
    expect(caretStepRight("$\\pi +1$", 1)).toBe(5);
    expect(caretStepRight("$x\\in \\mathbb{R}$", 2)).toBe(6);
    expect(caretStepRight("$x\\in \\mathbb{R}$", 6)).toBe(16);
  });

  it("moves one character in plain text", () => {
    expect(caretStepRight("abc", 1)).toBe(2);
    expect(caretStepLeft("abc", 1)).toBe(0);
  });
});
