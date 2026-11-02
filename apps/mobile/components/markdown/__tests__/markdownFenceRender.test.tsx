// Integration coverage for the fence dispatch/splice layer between parsed
// markdown and the Math*/Geometry*/FunctionGraphBlock rich components — zero
// coverage before this file (only each block's own logic was unit tested).
import { isValidElement, type ReactNode } from "react";
import { render, waitFor } from "@testing-library/react-native";

import { renderFence, type FenceNode } from "../markdownFenceRender";
import { renderRichFenceById } from "@/components/rich/RichFence";
import "@/lib/i18n";

// These check the English copy, so they read the real react-i18next over lib/i18n.
jest.unmock("react-i18next");

/** The React key a fence was drawn under; null when it drew nothing keyed. */
const keyOf = (rendered: ReactNode) => (isValidElement(rendered) ? rendered.key : null);

// markdownFenceRender.tsx statically imports CodeBlock/CopyBlock whichever
// fence branch runs; no-op fakes for the native modules they reach keep the
// import safe. Same pattern as MermaidBlock.test.tsx.
jest.mock("expo-web-browser", () => ({
  openBrowserAsync: jest.fn(),
}));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
// This suite's jest env cannot evaluate React.lazy dynamic import(). Eager
// stand-ins keep geometry/graph dispatch coverage without vm-modules.
jest.mock("@/components/rich/LazyHeavyRich", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const React = require("react");
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const { GeometryBlock } = require("@/components/rich/GeometryBlock");
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const { FunctionGraphBlock } = require("@/components/rich/FunctionGraphBlock");
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const { Molecule3DBlock } = require("@/components/rich/Molecule3DBlock");
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest mock factory
  const { Text: RNText } = require("react-native");
  return {
    ...jest.requireActual("@/components/rich/LazyHeavyRich"),
    LazyGeometryBlock: ({ content }: { content: string }) =>
      React.createElement(GeometryBlock, { content }),
    LazyFunctionGraphBlock: ({ content }: { content: string }) =>
      React.createElement(FunctionGraphBlock, { content }),
    LazyMolecule3DBlock: ({ content }: { content: string }) =>
      React.createElement(Molecule3DBlock, { content }),
    LazyMoleculeCard: () => React.createElement(RNText, null, "molecule-card"),
    LazyCircularClockBlock: ({ content }: { content: string }) =>
      React.createElement(RNText, null, `lazy-clock:${content}`),
    LazyWebPreviewCodeBlock: ({ code, lang }: { code: string; lang: string }) =>
      React.createElement(RNText, null, `lazy-web:${lang}:${code}`),
  };
});
// Display math renders via MathJax-SVG now; this suite asserts fence
// dispatch, so stand in the native MathText fallback for MathBlock.
jest.mock("@/components/rich/MathSvgView", () => {
  const React = jest.requireActual("react");
  const { MathText } = jest.requireActual("@/components/rich/MathText");
  return {
    MathSvgView: ({ latex }: { latex: string }) => React.createElement(MathText, { latex }),
  };
});
// CodeBlock's real syntax-tokenizer loads via a dynamic import() that Jest's
// CJS transform can't resolve without --experimental-vm-modules — a stub
// that just echoes its props is enough to assert dispatch reached it.
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

function node(content: string, info?: string): FenceNode {
  return { key: "k", content, sourceInfo: info };
}

describe("renderFence math dispatch", () => {
  it("routes an explicit ```math fence to MathBlock", async () => {
    const { getByTestId, getByText, queryByText } = await render(<>{renderFence(node("x^2 + 1", "math"))}</>);
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(getByText(/\+ 1/)).toBeOnTheScreen();
    expect(queryByText("x² + 1")).toBeNull();
  });

  it("routes ```latex / ```tex the same as ```math (settled path)", async () => {
    const latex = await render(<>{renderFence(node("x^2 + 1", "latex"))}</>);
    expect(latex.getByTestId("math-script")).toHaveTextContent("2");
    const tex = await render(<>{renderFence(node("x^2 + 1", "tex"))}</>);
    expect(tex.getByTestId("math-script")).toHaveTextContent("2");
  });

  it("routes an untagged fence that looks like LaTeX to MathBlock", async () => {
    const { getByText } = await render(<>{renderFence(node("\\alpha + \\beta"))}</>);
    // No preview WebView in this test env (react-native-webview isn't
    // mocked/linked here) — MathText's plain-Text rendering path is used,
    // same fallback real devices hit outside a dev build.
    expect(getByText("α + β")).toBeOnTheScreen();
  });
});

describe("renderFence math key stability", () => {
  it("BUG FIX regression: identical latex gets the same React key across re-parses, not the volatile node.key react-native-markdown-display regenerates every parse", () => {
    // Simulates two independent parses of the same still-growing streaming
    // reply: react-native-markdown-display assigns a fresh node.key each
    // time, but MathBlock's WebView-backed renderer must not remount (a
    // full WebView reload, visible as a flicker) just because the wrapping
    // node.key changed while the underlying latex stayed identical.
    const first = renderFence(node("x^2 + 1", "math"));
    const second = renderFence({
      key: "a-totally-different-node-key-from-the-next-parse",
      content: "x^2 + 1",
      sourceInfo: "math",
    });

    expect(keyOf(first)).toBeTruthy();
    expect(keyOf(first)).toBe(keyOf(second));
  });

  it("gives different latex content different keys", () => {
    const a = renderFence(node("x^2 + 1", "math"));
    const b = renderFence(node("y^2 + 1", "math"));

    expect(keyOf(a)).not.toBe(keyOf(b));
  });

  it("BUG FIX regression: two fences with identical latex get distinct keys via tokenIndex (no duplicate React key warning)", () => {
    // Reported live: `\pm 2` appeared twice in one reply and React warned
    // "Encountered two children with the same key, `math:\pm 2`". The
    // content-derived key must be disambiguated by the fence's stable
    // tokenIndex so sibling MathBlocks don't collide, while remaining
    // stable across re-parses for the *same* fence.
    const first = renderFence({
      key: "k1",
      content: "\\pm 2",
      sourceInfo: "math",
      tokenIndex: 5,
    });
    const second = renderFence({
      key: "k2",
      content: "\\pm 2",
      sourceInfo: "math",
      tokenIndex: 9,
    });

    expect(keyOf(first)).toBeTruthy();
    expect(keyOf(first)).not.toBe(keyOf(second));
    // The same fence re-parsed (same content + same tokenIndex, fresh
    // volatile node.key) must keep its key — no MathBlock remount/flicker.
    const firstReparsed = renderFence({
      key: "a-fresh-volatile-node-key",
      content: "\\pm 2",
      sourceInfo: "math",
      tokenIndex: 5,
    });
    expect(keyOf(firstReparsed)).toBe(keyOf(first));
  });

  it("BUG FIX regression: two identical non-heuristic ```math bodies still get distinct keys", () => {
    // `2 + 2` does not satisfy looksLikeLatexFence, so dispatch goes through
    // RichFence's math branch — that branch must also thread tokenIndex.
    const first = renderFence({
      key: "k1",
      content: "2 + 2",
      sourceInfo: "math",
      tokenIndex: 1,
    });
    const second = renderFence({
      key: "k2",
      content: "2 + 2",
      sourceInfo: "math",
      tokenIndex: 2,
    });
    expect(keyOf(first)).toBeTruthy();
    expect(keyOf(first)).not.toBe(keyOf(second));
  });
});

describe("renderFence geometry/graph dispatch", () => {
  it("routes an explicit ```geometry fence to GeometryBlock", async () => {
    const content = JSON.stringify({ type: "square", side: 5, unit: "cm" });
    const { toJSON } = await render(<>{renderFence(node(content, "geometry"))}</>);
    await waitFor(() => {
      expect(JSON.stringify(toJSON())).toContain("RNSVGSvgView");
    });
  });

  it("routes an explicit ```graph fence to FunctionGraphBlock", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [0, 0],
        [1, 1],
      ],
    });
    const { getByDisplayValue, getByTestId } = await render(
      <>{renderFence(node(content, "graph"))}</>,
    );
    await waitFor(() => {
      expect(getByDisplayValue("y = x^2")).toBeOnTheScreen();
      expect(getByTestId("graph-expand")).toBeOnTheScreen();
    });
  });

  it("sniffs an untagged ```json geometry blob and routes it to GeometryBlock", async () => {
    // The model routinely emits ```json (or an untagged fence) instead of
    // the ```geometry it's told to use — RichFence's content-sniffing
    // fallback (detectJsonRichFenceKind) must still route it correctly.
    const content = JSON.stringify({ type: "rectangle", width: 6, height: 4, unit: "cm" });
    const { toJSON } = await render(<>{renderFence(node(content, "json"))}</>);
    await waitFor(() => {
      expect(JSON.stringify(toJSON())).toContain("RNSVGSvgView");
    });
  });

  it("sniffs an untagged fence graph blob and routes it to FunctionGraphBlock", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "sin(x)",
      points: [
        [0, 0],
        [1, 0.84],
      ],
    });
    const { getByDisplayValue, getByTestId } = await render(
      <>{renderFence(node(content))}</>,
    );
    await waitFor(() => {
      expect(getByDisplayValue("y = sin(x)")).toBeOnTheScreen();
      expect(getByTestId("graph-expand")).toBeOnTheScreen();
    });
  });
});

describe("renderFence edge cases", () => {
  it("routes HTML preview fences through the lazy web preview boundary", async () => {
    const { getByText } = await render(
      <>{renderFence(node("<main>Hello</main>", "html"))}</>,
    );
    expect(getByText("lazy-web:html:<main>Hello</main>")).toBeOnTheScreen();
  });

  it("routes clock fences through the lazy clock boundary", async () => {
    const { getByText } = await render(
      <>{renderFence(node("America/New_York", "clock"))}</>,
    );
    expect(getByText("lazy-clock:America/New_York")).toBeOnTheScreen();
  });

  it("keeps registry clock dispatch behind the lazy clock boundary", async () => {
    const { getByText } = await render(
      <>{renderRichFenceById("clock", "clock", "UTC", "clock-key")}</>,
    );
    expect(getByText("lazy-clock:UTC")).toBeOnTheScreen();
  });

  it("renders nothing for a whitespace-only fence body", () => {
    expect(renderFence(node("   \n  "))).toBeNull();
  });

  it("hides invented ```image prompt fences (not a real rich block)", () => {
    expect(renderFence(node('{"prompt":"a cute cat"}', "image"))).toBeNull();
  });

  it("renders leaked message-fence instructions as prose, not a draft card", async () => {
    const leaked =
      "fence!\n(Or paste their number if SMS and you want it formatted for texting.)";
    const { getByText, queryByText } = await render(
      <>{renderFence(node(leaked, "message"))}</>,
    );
    expect(queryByText(/fence!/i)).toBeNull();
    expect(getByText(/paste their number/i)).toBeOnTheScreen();
    expect(queryByText("rich.message_draft")).toBeNull();
  });

  it("falls back to CodeBlock for a plain code fence with an explicit language", async () => {
    const { getByText } = await render(<>{renderFence(node("const x = 1;", "javascript"))}</>);
    expect(getByText("javascript:const x = 1;")).toBeOnTheScreen();
  });

  it("BUG FIX: an explicit ```python fence is never reinterpreted as an Answer", async () => {
    const { getByText, queryByLabelText } = await render(
      <>{renderFence(node("x = 2", "python"))}</>,
    );
    expect(getByText("python:x = 2")).toBeOnTheScreen();
    expect(queryByLabelText(/Answer:/)).toBeNull();
  });

  it("routes a short numeric final (including mis-tagged ```copy) to math, not Copy or a card", async () => {
    // Only the server's marked ```answer earns the answer card and its check.
    const { getByText, queryByLabelText, queryByText } = await render(
      <>{renderFence(node("120", "copy"))}</>,
    );
    expect(getByText(/120/)).toBeOnTheScreen();
    expect(queryByLabelText(/Answer:/)).toBeNull();
    expect(queryByText("Copy")).toBeNull();
  });

  it("routes the server's marked ```answer fence to AnswerBlock", async () => {
    const { getByLabelText } = await render(
      <>{renderFence(node("verified: true\n120", "answer"))}</>,
    );
    expect(getByLabelText("Answer: 120")).toBeOnTheScreen();
  });

  it("draws an unmarked ```answer fence as the card, without its header lines or the check", async () => {
    const { getByLabelText, queryByTestId, queryByText } = await render(
      <>{renderFence(node("label: answer\n120", "answer"))}</>,
    );
    expect(getByLabelText("Answer: 120")).toBeOnTheScreen();
    expect(queryByTestId("answer-success-check")).toBeNull();
    expect(queryByText(/label/)).toBeNull();
  });

  it("routes a factorial definition (mis-tagged ```copy) to MathBlock without Copy", async () => {
    const { getByText, queryByText } = await render(
      <>{renderFence(node("0! = 1", "copy"))}</>,
    );
    expect(getByText(/0!/)).toBeOnTheScreen();
    expect(queryByText("Copy")).toBeNull();
  });

  it("BUG FIX regression: routes a bare simplified expression with no lang tag or ```copy to math, not Copy", async () => {
    // Reported live: "2c^2" (a simplified final result, no "=") fell through
    // every existing looksLikeMathAnswer branch and landed on the generic
    // CodeBlock fallback, which shows a "Copy" button.
    const { getByTestId, queryByLabelText, queryByText } = await render(
      <>{renderFence(node("2c^2", "copy"))}</>,
    );
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(queryByLabelText(/Answer:/)).toBeNull();
    expect(queryByText("Copy")).toBeNull();
  });

  it("BUG FIX regression: an explicit ```math fence is never reinterpreted as an Answer even if its content looks answer-like", async () => {
    // looksLikeMathAnswer was broadened to catch bare expressions like
    // "2c^2" — without a lang guard at the call site, that same heuristic
    // started misrouting explicitly ```math-tagged content (e.g. "x^2 + 1",
    // a legitimate intermediate step) to AnswerBlock instead of MathBlock.
    const { getByTestId, queryByText } = await render(<>{renderFence(node("x^2 + 1", "math"))}</>);
    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(queryByText("x² + 1")).toBeNull();
  });

  it("BUG FIX regression: a multi-solution final ($x = 2$ or $x = -2$) in a ```copy fence routes to AnswerBlock, not the fallback Copy/Code box", async () => {
    // Models routinely emit both quadratic roots as the final answer, often
    // with each term wrapped in $...$ and sometimes mis-tagged ```copy. The
    // literal `$` chars used to fail every detector and drop it onto the
    // fallback CodeBlock — raw `$` signs, syntax-highlighted numbers, and a
    // Copy button. It must render as math (no Copy), and not as the server's
    // checked answer card, which only a marked ```answer fence gets.
    const { queryByLabelText, queryByText } = await render(
      <>{renderFence(node("$x = 2$ or $x = -2$", "copy"))}</>,
    );
    expect(queryByLabelText(/Answer:/)).toBeNull();
    expect(queryByText("Copy")).toBeNull();
  });

  it("BUG FIX regression: an untagged multi-solution final (x = 2 or x = -2, no $ wraps) routes to math", async () => {
    const { queryByLabelText, queryByText } = await render(
      <>{renderFence(node("x = 2 or x = -2"))}</>,
    );
    expect(queryByLabelText(/Answer:/)).toBeNull();
    expect(queryByText("Copy")).toBeNull();
  });

  it("BUG FIX regression: an explicit ```answer fence routes to AnswerBlock via node.sourceInfo even when the content doesn't match any content-shape heuristic (trailing unit)", async () => {
    // Reported live: react-native-markdown-display's AST exposes the fence
    // language as `sourceInfo` (tokensToAST.js), not `info`. renderFence used
    // to read `node.info`, which is always undefined — every explicit fence
    // tag was silently dropped and routing fell back entirely to
    // looksLikeMathAnswer's content-shape heuristic, which doesn't recognize
    // a value followed by a trailing unit ("cm") as answer-shaped. Confirmed
    // via a live console.log of the real node shape from react-native-markdown-display.
    const { getByLabelText, queryByText } = await render(
      <>{renderFence(node("verified: true\n$c \\approx 7.21$ cm", "answer"))}</>,
    );
    expect(getByLabelText(/Answer:/)).toBeOnTheScreen();
    expect(queryByText("Copy")).toBeNull();
  });

  it("BUG FIX regression: an explicit ```answer fence with a leading currency sign ($30, no closing $) routes to AnswerBlock", async () => {
    const { getByLabelText, queryByText } = await render(
      <>{renderFence(node("verified: true\n$30", "answer"))}</>,
    );
    expect(getByLabelText(/Answer:/)).toBeOnTheScreen();
    expect(queryByText("Copy")).toBeNull();
  });

  it("routes an explicit ```molecule3d fence to Molecule3DBlock (not CodeBlock)", async () => {
    // The fence lang "molecule3d" contains a digit — takeLang used to
    // only read [a-zA-Z-], splitting it into "molecule" + "3d". The
    // fence then fell through to a plain CodeBlock instead of the 3D
    // molecule viewer.
    const sdf = `O2\n     RDKit          3D\n\n  2  1  0  0  0  0  0  0  0  0999 V2000\n    0.5705    0.0000    0.0000 O   0  0  0  0  0  0\n   -0.5705    0.0000    0.0000 O   0  0  0  0  0  0\n  1  2  2  0\nM  END`;
    const { getByText, queryByText } = await render(
      <>{renderFence(node(sdf, "molecule3d"))}</>,
    );
    expect(getByText("Ball")).toBeTruthy();
    // Must NOT fall through to a CodeBlock with "molecule3d" badge.
    expect(queryByText("molecule3d")).toBeNull();
  });

  it("routes a ```molecule fence to MoleculeCard (not CodeBlock or Molecule3DBlock)", async () => {
    const body = JSON.stringify({ smiles: "CCO", caption: "Ethanol" });
    const { getByText, queryByText } = await render(
      <>{renderFence(node(body, "molecule"))}</>,
    );
    expect(getByText("molecule-card")).toBeTruthy();
    expect(queryByText("molecule")).toBeNull();
    expect(queryByText("Ball")).toBeNull();
  });

  it("does not fall through malformed ```places JSON to CodeBlock", async () => {
    const { queryByText, getByText } = await render(
      <>{renderFence(node("{not-json", "places"))}</>,
    );
    expect(queryByText("places:{not-json")).toBeNull();
    expect(getByText("{not-json")).toBeOnTheScreen();
  });
});
