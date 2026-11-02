/**
 * Structural guard: every lint or type suppression says why (code-health audit CLAR-06).
 *
 * 13 of 29 ESLint disables gave no reason, though the engineering standards ask for one,
 * so nobody could tell a deliberate exception from a silenced bug. A disable carries its
 * reason after ` -- ` on the same line (ESLint's own description syntax), and a
 * `@ts-expect-error` or `@ts-ignore` carries text after the directive.
 */

import { appFiles, readSource, relative, rootFiles } from "@/lib/__tests__/support/sourceFiles";

const ESLINT = /(?:\/\/|\/\*)\s*eslint-disable(?:-next-line|-line)?\b(?<rest>[^\n]*)/;
const TYPESCRIPT = /(?:\/\/|\/\*)\s*@ts-(?:expect-error|ignore)\b(?<rest>[^\n]*)/;
/** This file's own examples are suppressions on purpose. */
const SELF = "lib/__tests__/suppressionReasons.test.ts";

/** 1-based lines whose suppression gives no reason. */
function silentSuppressions(text: string): number[] {
  const found: number[] = [];
  text.split("\n").forEach((line, index) => {
    const eslint = ESLINT.exec(line);
    if (eslint && !/\s--\s+\S/.test(eslint.groups?.rest ?? "")) found.push(index + 1);
    const typescript = TYPESCRIPT.exec(line);
    if (typescript && !/\S/.test((typescript.groups?.rest ?? "").replace(/\*\/\s*$/, ""))) {
      found.push(index + 1);
    }
  });
  return found;
}

describe("suppression reasons", () => {
  it("sees a suppression without a reason", () => {
    expect(silentSuppressions("// eslint-disable-next-line react-hooks/exhaustive-deps")).toEqual([1]);
    expect(silentSuppressions("/* eslint-disable react-hooks/refs */")).toEqual([1]);
    expect(silentSuppressions("// @ts-expect-error")).toEqual([1]);
    expect(
      silentSuppressions(
        "// eslint-disable-next-line react-hooks/exhaustive-deps -- reseed only when it opens\n" +
          "/* eslint-disable react-hooks/refs -- read on touch */\n" +
          "// @ts-expect-error the stub has no types",
      ),
    ).toEqual([]);
  });

  it("every suppression in the app says why", () => {
    const silent = [...appFiles(), ...rootFiles()]
      .filter((file) => relative(file) !== SELF)
      .flatMap((file) => silentSuppressions(readSource(file)).map((line) => `${relative(file)}:${line}`));
    expect(silent).toEqual([]);
  });
});
