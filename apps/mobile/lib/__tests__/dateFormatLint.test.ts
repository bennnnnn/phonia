/**
 * The date lint (eslint.config.js, `no-restricted-properties`): outside lib/datetime a
 * date or time is formatted with `formatDate`, never `toLocale*String` or
 * `Intl.DateTimeFormat`. Sixteen screens wrote dates in the phone's locale and seven
 * in the app's language, so one to-do read "23:30" in its row and "11:30 PM" in its
 * editor. Runs the real config.
 */
import { ROOT } from "@/lib/__tests__/support/sourceFiles";

type LintMessage = { line: number; ruleId: string | null };
type FlatLinter = { verify: (code: string, config: unknown, filename: string) => LintMessage[] };

// eslint-disable-next-line @typescript-eslint/no-require-imports -- eslint and its config are CommonJS, and the lib project has no @types/node
const { Linter } = require("eslint") as { Linter: new (options: { configType: "flat"; cwd: string }) => FlatLinter };
// eslint-disable-next-line @typescript-eslint/no-require-imports -- the config is CommonJS, as above
const config = require("../../eslint.config.js") as unknown;

const linter = new Linter({ configType: "flat", cwd: ROOT });

function flagged(code: string, file: string): number[] {
  return linter
    .verify(code, config, `${ROOT}/${file}`)
    .filter((message) => message.ruleId === "no-restricted-properties")
    .map((message) => message.line);
}

const DIRECT = [
  "const a = due.toLocaleTimeString(locale, { hour: \"numeric\" });",
  "const b = due.toLocaleDateString();",
  "const c = due.toLocaleString(\"de\");",
  "const d = new Intl.DateTimeFormat(locale, { month: \"short\" }).format(due);",
  "const e = new Intl.RelativeTimeFormat(locale).format(-1, \"day\");",
  "const { DateTimeFormat } = Intl;",
].join("\n");

describe("date lint", () => {
  it.each([
    "features/todos/components/TodoRow.tsx",
    "ui/pickers/TimePickerDialog.tsx",
    "lib/money/format.ts",
    "lib/clockTime.ts",
    "components/rich/CircularClockBlock.tsx",
  ])("flags every direct formatter in %s", (file) => {
    expect(flagged(DIRECT, file)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("leaves the helper, its types and other Intl formatters alone", () => {
    const code = [
      "const f = formatDate(due, \"time\");",
      "const options: Intl.DateTimeFormatOptions = { hour: \"numeric\" };",
      "let cached: Intl.DateTimeFormat | null = null;",
      "const n = new Intl.NumberFormat(locale).format(3);",
      "const l = new Intl.ListFormat(locale).format(names);",
    ].join("\n");
    expect(flagged(code, "features/todos/components/TodoRow.tsx")).toEqual([]);
  });

  it.each(["lib/datetime/format.ts", "lib/datetime/phoneClock.ts", "features/todos/components/__tests__/TodoRow.test.tsx"])(
    "exempts %s",
    (file) => {
      expect(flagged(DIRECT, file)).toEqual([]);
    },
  );
});
