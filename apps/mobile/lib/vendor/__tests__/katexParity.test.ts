import katex from "katex";

// The lib test project includes Jest types, but no global Node type package.
// These test-only native helpers have deliberately small typed interfaces.
declare const __dirname: string;
const { createHash } = jest.requireActual<{
  createHash(name: string): { update(value: string): { digest(encoding: string): string } };
}>("node:crypto");
const { readFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8" | "base64"): string;
}>("node:fs");
const { dirname, join } = jest.requireActual<{
  dirname(path: string): string;
  join(...parts: string[]): string;
}>("node:path");
const { createRequire } = jest.requireActual<{
  createRequire(path: string): { resolve(name: string): string };
}>("node:module");
const packageDir = dirname(createRequire(join(__dirname, "katexParity.test.ts")).resolve("katex/package.json"));
const sourceCss = readFileSync(join(packageDir, "dist/katex.min.css"), "utf8");
const manifest = JSON.parse(readFileSync(join(__dirname, "../manifest.json"), "utf8"));
/** The stylesheet PDF export inlines (features/chat/model/printDocument.ts), as shipped. */
const KATEX_CSS = readFileSync(join(__dirname, "../katex.min.css.txt"), "utf8");
const facePattern = /@font-face\{[^}]*\}/g;
const sha = (value: string): string => createHash("sha256").update(value).digest("hex");

describe("KaTeX renderer and offline CSS/font parity", () => {
  it("records the installed renderer version and committed CSS hash", () => {
    expect(manifest.versions.katex).toBe(katex.version);
    expect(KATEX_CSS).toContain(`content:"${katex.version}"`);
    expect(manifest.sha256.katexCss).toBe(sha(KATEX_CSS).slice(0, 16));
  });

  it("keeps every non-font layout rule identical to the installed renderer CSS", () => {
    // A renderer update renamed sizing/strut/base classes;0.17 CSS with0.18
    // markup made inverse-matrix brackets short and fraction rows overlap.
    expect(sha(KATEX_CSS.replace(facePattern, ""))).toBe(sha(sourceCss.replace(facePattern, "")));
  });

  it("embeds matching fonts in complete, valid scalar src declarations", () => {
    const originals = sourceCss.match(facePattern) ?? [];
    const bundled = KATEX_CSS.match(facePattern) ?? [];
    expect(bundled.length).toBe(originals.length);
    expect(bundled.length).toBeGreaterThan(0);
    bundled.forEach((face, index) => {
      const original = originals[index];
      const file = original.match(/url\(fonts\/([A-Za-z0-9_-]+\.woff2)\)/)?.[1];
      expect(file).toBeDefined();
      // Consumes the full src value: trailing ')' from the old partial
      // woff/ttf removal is invalid CSS and must fail this assertion.
      const src = face.match(/src:([^}]+)\}$/)?.[1];
      const font = src?.match(/^url\(data:font\/woff2;base64,([A-Za-z0-9+/=]+)\) format\("woff2"\)$/)?.[1];
      expect(font).toBeDefined();
      expect(sha(font!)).toBe(sha(readFileSync(join(packageDir, "dist/fonts", file!), "base64")));
      expect(face.replace(/src:[^}]+/, "")).toBe(original.replace(/src:[^}]+/, ""));
    });
    expect(KATEX_CSS).not.toContain("url(fonts/");
  });

  it("provides the sizing classes emitted for the actual inverse-matrix answer", () => {
    const latex = String.raw`\left[\begin{matrix}-2 & 1\\\frac{3}{2} & - \frac{1}{2}\end{matrix}\right]`;
    const html = katex.renderToString(latex, { displayMode: true, output: "html" });
    for (const name of ["katex-base", "katex-strut", "katex-sizing"]) {
      expect(html).toContain(name);
      expect(KATEX_CSS).toContain(`.${name}`);
    }
    expect(html).not.toContain("katex-error");
  });
});
