/**
 * The design lint (eslint.config.js, `no-restricted-syntax`) sees a raw color however
 * it is written: a JSX prop, a module constant, a ternary branch, an rgba() or named
 * ink, a color built in a template string. Before, it saw only a hex written straight
 * into a style key, and six colors in screens slipped past it. Palettes, masks and
 * strings that only look like colors stay allowed. Runs the real config.
 */
import { ROOT } from "@/lib/__tests__/support/sourceFiles";

type LintMessage = { line: number; ruleId: string | null };
type FlatLinter = { verify: (code: string, config: unknown, filename: string) => LintMessage[] };

// eslint-disable-next-line @typescript-eslint/no-require-imports -- eslint and its config are CommonJS, and the lib project has no @types/node
const { Linter } = require("eslint") as { Linter: new (options: { configType: "flat"; cwd: string }) => FlatLinter };
// eslint-disable-next-line @typescript-eslint/no-require-imports -- the config is CommonJS, as above
const config = require("../../eslint.config.js") as unknown;

const linter = new Linter({ configType: "flat", cwd: ROOT });

/** 1-based lines the design rules flag in `code`, linted as if it were `file`. */
function flagged(code: string, file = "features/demo/components/Demo.tsx"): number[] {
  return linter
    .verify(code, config, `${ROOT}/${file}`)
    .filter((message) => message.ruleId === "no-restricted-syntax")
    .map((message) => message.line);
}

/** The 1-based numbers of the lines that end with `// flag`. */
function marked(code: string): number[] {
  return code
    .split("\n")
    .flatMap((line, index) => (line.endsWith("// flag") ? [index + 1] : []));
}

describe("design lint: raw colors", () => {
  it("flags a color however a screen writes it", () => {
    const code = [
      'const INK = "#FFFFFF"; // flag',
      'const a = <ActivityIndicator color="#fff" />; // flag',
      'const b = { color: on ? "#111113" : theme.text }; // flag',
      'const c = { backgroundColor: "rgba(0,0,0,0.5)" }; // flag',
      'const d = <Rect fill="white" />; // flag',
      "const e = `#${hex}`; // flag",
      "const f = `rgba(${r}, ${g}, ${b}, 0.5)`; // flag",
      "const g = { backgroundColor: `${theme.bg}FA` }; // flag",
    ].join("\n");
    expect(flagged(code)).toEqual(marked(code));
  });

  it("leaves strings that only look like colors alone", () => {
    const code = [
      'const a = { backgroundColor: "transparent", borderColor: withAlpha(theme.text, 0.5) };',
      "const heading = `# ${title}`;",
      "const mask = `url(#${maskId})`;",
      'const hash = "#";',
      'const anchor = "#add-row";',
      'const fill = <Path fill="none" stroke={theme.text} />;',
    ].join("\n");
    expect(flagged(code)).toEqual([]);
  });

  it("lets palettes and masks keep their colors, and still holds them to the spacing scale", () => {
    expect(flagged('export const PRIMARY = "#4F56E5";', "lib/accent.ts")).toEqual([]);
    expect(flagged('const keep = <Rect fill="white" />;', "ui/icons/custom.tsx")).toEqual([]);
    expect(flagged("const s = { padding: 6 };", "lib/codeHighlight.ts")).toEqual([1]);
  });
});

describe("design lint: icon sizes", () => {
  it("flags an icon drawn at a raw size, not one on the ladder or an avatar", () => {
    const code = [
      'const a = <Icon name="close" size={18} />; // flag',
      "const b = <WaveformIcon size={24} color={theme.text} />; // flag",
      'const c = <Icon name="close" size={IconSize.sm} />;',
      "const d = <Avatar name={name} size={32} />;",
    ].join("\n");
    expect(flagged(code)).toEqual(marked(code));
  });
});
