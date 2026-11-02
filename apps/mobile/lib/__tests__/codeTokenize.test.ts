import { TOKEN_COLORS } from "@/lib/codeHighlight";
import {
  guessLang,
  highlightPlainChunk,
  looksLikeC,
  looksLikeJava,
  MAX_PLAIN_HIGHLIGHT_CHARS,
  resolveHighlightLang,
  tokenize,
} from "@/lib/codeTokenize";

describe("resolveHighlightLang", () => {
  it("trusts an explicit, known fence language", () => {
    expect(resolveHighlightLang("python", "x = 1")).toBe("python");
  });

  it("falls back to guessing when the fence language is unknown", () => {
    expect(resolveHighlightLang("made-up-lang", "def add(a, b):\n    return a + b")).toBe(
      "python",
    );
  });
});

describe("guessLang", () => {
  it("guesses python from indentation-style syntax", () => {
    expect(guessLang("def add(a, b):\n    return a + b")).toBe("python");
  });

  it("guesses json from an object literal", () => {
    expect(guessLang('{"foo": "bar"}')).toBe("json");
  });

  it("guesses go from a func declaration", () => {
    expect(guessLang("func main() {\n  fmt.Println(\"hi\")\n}")).toBe("go");
  });
});

describe("looksLikeJava / looksLikeC", () => {
  it("detects a Java main method", () => {
    expect(looksLikeJava("public static void main(String[] args) {}")).toBe(true);
  });

  it("detects a C include", () => {
    expect(looksLikeC("#include <stdio.h>\nint main() { return 0; }")).toBe(true);
  });

  it("rejects unrelated text", () => {
    expect(looksLikeJava("hello world")).toBe(false);
    expect(looksLikeC("hello world")).toBe(false);
  });
});

describe("tokenize", () => {
  it("keeps a tagged python solution scannable", () => {
    const code = [
      "def two_sum(nums, target):",
      "    for i, num in enumerate(nums):",
      "        if num in seen:",
      "            return [seen[num], i]",
      "    return []",
    ].join("\n");
    const tokens = tokenize(code, "python");
    expect(tokens.map((t) => t.text).join("")).toBe(code);
    const color = (word: string) => tokens.find((t) => t.text === word)?.color;
    expect(color("def")).toBe(TOKEN_COLORS.keyword);
    expect(color("for")).toBe(TOKEN_COLORS.keyword);
    expect(color("if")).toBe(TOKEN_COLORS.keyword);
    expect(color("in")).toBe(TOKEN_COLORS.keyword);
    expect(color("return")).toBe(TOKEN_COLORS.keyword);
    // Names stay in the body ink, even when punctuation shares their run.
    expect(tokens.find((t) => t.text.includes("nums"))?.color).toBe(TOKEN_COLORS.plain);
    expect(tokens.find((t) => t.text.includes("target"))?.color).toBe(TOKEN_COLORS.plain);
  });

  it("returns colored tokens for a known language", () => {
    const tokens = tokenize("const x = 1;", "javascript");
    expect(tokens.length).toBeGreaterThan(0);
    expect(tokens.map((t) => t.text).join("")).toBe("const x = 1;");
  });

  it("returns a single plain token for an empty string", () => {
    expect(tokenize("", "javascript")).toEqual([]);
  });

  it("falls back to plain text for a language with no grammar", () => {
    const tokens = tokenize("whatever content", "totally-unknown-lang-xyz");
    expect(tokens.map((t) => t.text).join("")).toBe("whatever content");
  });
});

describe("highlightPlainChunk", () => {
  it("returns a single plain token when input exceeds the cap", () => {
    const text = `${"x".repeat(MAX_PLAIN_HIGHLIGHT_CHARS + 1)} const y = 1;`;
    const tokens = highlightPlainChunk(text, "javascript");
    expect(tokens).toEqual([{ text, color: TOKEN_COLORS.plain }]);
  });

  it("colors python keywords and leaves names in the body ink", () => {
    const text = 'flag = True\nname = "john"\n';
    const tokens = highlightPlainChunk(text, "python");
    expect(tokens.find((t) => t.text === "True")?.color).toBe(TOKEN_COLORS.keyword);
    expect(tokens.find((t) => t.text.includes("john"))?.color).toBe(TOKEN_COLORS.string);
    expect(tokens.find((t) => t.text.includes("name"))?.color).toBe(TOKEN_COLORS.plain);
    expect(tokens.find((t) => t.text.includes("flag"))?.color).toBe(TOKEN_COLORS.plain);
  });

  it("still highlights keywords on medium-sized input under the cap", () => {
    const text = `// note\n${"x ".repeat(200)}const answer = 42;`;
    expect(text.length).toBeLessThanOrEqual(MAX_PLAIN_HIGHLIGHT_CHARS);
    const tokens = highlightPlainChunk(text, "javascript");
    expect(tokens.some((t) => t.text === "const" && t.color === TOKEN_COLORS.keyword)).toBe(
      true,
    );
    expect(tokens.some((t) => t.text === "42" && t.color === TOKEN_COLORS.number)).toBe(true);
  });
});
