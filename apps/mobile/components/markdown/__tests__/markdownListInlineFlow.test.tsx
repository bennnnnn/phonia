// BUG FIX regression: a tight list (the model's default — consecutive
// `- item` lines, no blank lines between them) strips each item's paragraph
// wrapper (markdown-display's omitListItemParagraph). Without that
// paragraph's single enclosing Text, a list item's `textgroup` rendered as
// a bare Fragment, so "lead-in text" + "**bold span**" + "trailing text"
// landed as three separate sibling Text nodes directly inside list_item's
// row View — and sibling Text nodes in a View each get their own line in
// React Native. A reply like:
//   - Germany invaded Poland on **September 1, 1939**; Britain and France
//     declared war days later.
// rendered as three stacked lines ("Germany invaded Poland on" /
// "September 1, 1939" / "; Britain and France declared war days later.")
// instead of one wrapped sentence, with the continuation stranding on its
// own line behind an orphaned punctuation mark.
import { render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

jest.mock("@/components/LinkPreviewCard", () => ({
  LinkPreviewCard: "LinkPreviewCard",
}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({
  WebPreviewCodeBlock: "WebPreviewCodeBlock",
}));
jest.mock("@/components/rich/CircularClockBlock", () => ({
  CircularClockBlock: "CircularClockBlock",
}));
jest.mock("@/components/rich/AnswerBlock", () => ({
  AnswerBlock: "AnswerBlock",
}));
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

/**
 * Walk up through every consecutive <Text> ancestor and return the outermost
 * one reached before hitting a <View> (or the root). Two text runs sharing
 * the same outermost Text render as one inline paragraph; runs whose
 * outermost Text differs are separate sibling blocks — each gets its own
 * line in React Native, which is exactly the bug this file guards against.
 */
function outermostTextAncestor(node: { type?: string; parent?: unknown }) {
  let cur = node.parent as typeof node | undefined;
  let last: typeof node | null = null;
  while (cur) {
    if (cur.type === "Text") {
      last = cur;
      cur = cur.parent as typeof node | undefined;
      continue;
    }
    break;
  }
  return last;
}

describe("markdown list item inline flow", () => {
  it("keeps lead-in text, a bold span, and trailing text on one inline run", async () => {
    const md =
      "- Germany invaded Poland on **September 1, 1939**; Britain and France declared war days later.";
    const { getByText } = await render(<MarkdownContent content={md} />);

    const before = getByText(/Germany invaded Poland on/);
    const bold = getByText("September 1, 1939");
    const after = getByText(/Britain and France declared war days later/);

    const beforeText = outermostTextAncestor(before as never);
    expect(beforeText).not.toBeNull();
    // The bold span and the trailing text share the same outermost Text as
    // the lead-in — one inline paragraph, not three stacked sibling blocks.
    expect(outermostTextAncestor(bold as never)).toBe(beforeText);
    expect(outermostTextAncestor(after as never)).toBe(beforeText);
  });

  it("keeps lead-in text, inline code, and trailing text on one inline run", async () => {
    const md =
      "- Generators produce items lazily with `yield`, so they're memory-friendly.";
    const { getByText } = await render(<MarkdownContent content={md} />);

    const before = getByText(/Generators produce items lazily with/);
    const code = getByText("yield");
    const after = getByText(/memory-friendly/);

    const beforeText = outermostTextAncestor(before as never);
    expect(beforeText).not.toBeNull();
    expect(outermostTextAncestor(code as never)).toBe(beforeText);
    expect(outermostTextAncestor(after as never)).toBe(beforeText);
  });

  it("keeps multiple inline-code spans in one list item on one run", async () => {
    const md = "- `__init__` vs `__new__`, `__str__` vs `__repr__`";
    const { getByText } = await render(<MarkdownContent content={md} />);

    const init = getByText("__init__");
    const neu = getByText("__new__");
    const outer = outermostTextAncestor(init as never);
    expect(outer).not.toBeNull();
    expect(outermostTextAncestor(neu as never)).toBe(outer);
    expect(outermostTextAncestor(getByText("__str__") as never)).toBe(outer);
  });

  it("keeps a bold-led ordered list item's continuation on the same run", async () => {
    const md =
      "1. **1941** — Germany invades the USSR; Japan attacks Pearl Harbor.";
    const { getByText } = await render(<MarkdownContent content={md} />);

    const bold = getByText("1941");
    const after = getByText(/Germany invades the USSR/);
    const boldOuter = outermostTextAncestor(bold as never);
    expect(boldOuter).not.toBeNull();
    expect(outermostTextAncestor(after as never)).toBe(boldOuter);
  });

  it("bolds the number of an item whose title sits on its own line", async () => {
    const md = [
      "1. **Read widely** – Consume diverse books and articles outside your comfort zone.",
      "2. **Prioritize sleep** – Aim for seven to nine hours every night.",
    ].join("\n");
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(StyleSheet.flatten(getByText("1.").props.style).fontFamily).toBe(
      "SourceSans3-Bold",
    );
    expect(getByText(/Consume diverse books/)).toBeTruthy();
  });

  it("keeps a plain numbered step's number regular", async () => {
    const md =
      "1. Preheat the oven to 200 degrees.\n2. Mix the flour and the butter.";
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(StyleSheet.flatten(getByText("1.").props.style).fontFamily).toBe(
      "SourceSans3",
    );
  });

  it("still renders a plain list item (no embedded styling) as before", async () => {
    const md =
      "- Root causes: Treaty of Versailles resentment and the Great Depression.";
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(getByText(/Root causes: Treaty of Versailles/)).toBeOnTheScreen();
  });
});
