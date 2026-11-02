/**
 * The native renderer's symbol and operator tables come from MathJax's own TeX
 * maps, so inline maths knows every symbol display maths does. This test
 * rebuilds them and fails when `lib/math/latexSymbols.generated.ts` is stale.
 * After upgrading mathjax-full run `pnpm latex-symbols` to rewrite the file.
 */
import { LATEX_OPERATOR_NAMES, LATEX_SYMBOLS } from "@/lib/math/latexSymbols.generated";
import { mathJaxSymbolTables } from "@/lib/math/__tests__/mathJaxTables";

// The lib test project has Jest types but no Node types (see licenses.test.ts).
declare const __dirname: string;
declare const process: { env: Record<string, string | undefined> };
const { readFileSync, writeFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8"): string;
  writeFileSync(path: string, data: string): void;
}>("node:fs");
const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");

const GENERATED = join(__dirname, "..", "latexSymbols.generated.ts");

function quote(value: string): string {
  return JSON.stringify(value).replace(/[\u0080-￿]/g, (ch) => {
    // Combining marks and invisible characters are unreadable in source.
    return /[\p{M}\p{Cf}\p{Zs}]/u.test(ch) ? `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}` : ch;
  });
}

function entries(table: Record<string, string>): string {
  return Object.keys(table)
    .sort()
    .map((name) => `  ${/^[A-Za-z_]\w*$/.test(name) ? name : quote(name)}: ${quote(table[name])},`)
    .join("\n");
}

function render(symbols: Record<string, string>, operators: Record<string, string>): string {
  return `// Generated from mathjax-full's TeX maps by lib/math/__tests__/latexSymbols.test.ts.
// Do not edit: run \`pnpm latex-symbols\` after upgrading mathjax-full.

/** \`\\name\` → the character MathJax draws for it. */
export const LATEX_SYMBOLS: Readonly<Record<string, string>> = {
${entries(symbols)}
};

/** \`\\name\` → the upright word MathJax sets for a function or operator name. */
export const LATEX_OPERATOR_NAMES: Readonly<Record<string, string>> = {
${entries(operators)}
};
`;
}

describe("generated LaTeX symbol tables", () => {
  const { symbols, operators } = mathJaxSymbolTables();
  const source = render(symbols, operators);

  if (process.env.UPDATE_LATEX_SYMBOLS) writeFileSync(GENERATED, source);

  it("match MathJax's maps (run `pnpm latex-symbols` to regenerate)", () => {
    expect(readFileSync(GENERATED, "utf8")).toBe(source);
  });

  it("never draw a character that reads as LaTeX source", () => {
    for (const [name, glyph] of Object.entries(LATEX_SYMBOLS)) {
      expect([name, glyph]).not.toEqual([name, expect.stringMatching(/\\|^\s*$/)]);
    }
    expect(LATEX_OPERATOR_NAMES.liminf).toBe("lim inf");
    expect(LATEX_SYMBOLS.varphi).toBe("φ");
    expect(LATEX_SYMBOLS.ell).toBe("ℓ");
    expect(LATEX_SYMBOLS.backslash).toBe("∖");
  });
});
