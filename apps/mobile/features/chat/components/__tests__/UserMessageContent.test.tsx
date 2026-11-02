// BUG FIX regression: the user's own sent message used to render as a bare
// <Text> with zero markdown/math processing, while the assistant's echoed
// version of the same content rendered fully (MarkdownContent handles both
// now). Sibling components pull in native modules (reanimated,
// expo-linear-gradient) unrelated to what this file tests — stubbed so
// import-time stays safe, mirroring markdownFenceRender.test.tsx's pattern.
import { act, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { UserMessageContent } from "@/features/chat/components/UserMessageContent";
import { AA, contrastRatio } from "@/lib/__tests__/support/contrast";
import { ACCENT_OPTIONS, DEFAULT_ACCENT } from "@/lib/accent";
import { setAccentSnapshot } from "@/lib/accentRuntime";
import type { Message } from "@/lib/api/types";

let mockScheme: "light" | "dark" = "light";
jest.mock("@/lib/colorScheme", () => ({
  useResolvedColorScheme: () => mockScheme,
}));

jest.mock("@/features/attachments/components/ChatMessageImage", () => ({
  ChatMessageImage: "ChatMessageImage",
}));
jest.mock("@/features/attachments/components/ChatMessagePdf", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    ChatMessagePdf: ({ fileName }: { fileName: string }) => <RNText>{`pdf:${fileName}`}</RNText>,
  };
});
jest.mock("@/features/chat/components/CollapsibleMessageBody", () => {
  const { View } = jest.requireActual("react-native");
  return {
    CollapsibleMessageBody: ({ children }: { children: React.ReactNode }) => (
      <View>{children}</View>
    ),
  };
});
// LinkPreviewCard (unrelated to math/markdown rendering) transitively pulls
// in expo-constants/expo-secure-store/network config — stub it directly
// rather than chasing that whole unrelated chain.
jest.mock("@/components/LinkPreviewCard", () => ({
  LinkPreviewCard: "LinkPreviewCard",
}));
type MockIndexStatus = { indexed: boolean; failed: boolean; fileName?: string | null };
const mockIndexStatus = jest.fn(
  (_attachmentId?: string | null): MockIndexStatus => ({ indexed: true, failed: false }),
);
jest.mock("@/features/attachments/hooks/useAttachmentIndexed", () => ({
  useAttachmentIndexed: (attachmentId?: string | null) => mockIndexStatus(attachmentId),
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
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

function userMessage(content: string): Message {
  return {
    id: "m1",
    role: "user",
    content,
    model: null,
    created_at: new Date().toISOString(),
  };
}

describe("UserMessageContent math/markdown rendering", () => {
  it("renders a bare equation as typeset math, not literal text", async () => {
    const { getByText, getByTestId, queryByText } = await render(
      <UserMessageContent message={userMessage("x^2 + 2 = 6")} />,
    );

    expect(getByTestId("math-script")).toHaveTextContent("2");
    expect(getByText(/\+ 2 = 6/)).toBeOnTheScreen();
    expect(queryByText("x^2 + 2 = 6")).toBeNull();
    expect(queryByText("x² + 2 = 6")).toBeNull();
  });

  it("keeps grouped slash fractions unambiguous in a sent user bubble", async () => {
    const { getByTestId, queryByText } = await render(
      <UserMessageContent
        message={userMessage("Simplify (x^2 - 4)/(x^2 - x - 2).")}
      />,
    );
    expect(getByTestId("math-frac")).toBeOnTheScreen();
    expect(queryByText("x² - 4/x² - x - 2")).toBeNull();
  });

  it("spaces a bare unspaced equation the user typed", async () => {
    const { getByText } = await render(
      <UserMessageContent message={userMessage("x=3")} />,
    );
    expect(getByText("x=3")).toBeOnTheScreen();
  });

  it("shows 6\\sqrt{4} as typed, not a 6th root", async () => {
    const { queryByText, getByTestId } = await render(
      <UserMessageContent message={userMessage("$6\\sqrt{4}$")} />,
    );
    expect(queryByText(/√\[6\]/)).toBeNull();
    expect(queryByText(/\\times/)).toBeNull();
    expect(getByTestId("math-draft-preview")).toBeOnTheScreen();
  });

  it("does not format $|5|3$ into a markdown table", async () => {
    const { getByTestId, queryByText, queryByTestId } = await render(
      <UserMessageContent message={userMessage("$|5|3$")} />,
    );
    expect(getByTestId("math-draft-preview")).toBeOnTheScreen();
    expect(getByTestId("math-abs")).toBeOnTheScreen();
    expect(queryByText("---")).toBeNull();
    expect(queryByTestId("math-slot-before-caret")).toBeNull();
  });

  it("renders markdown emphasis instead of literal asterisks", async () => {
    const { getByText, queryByText } = await render(
      <UserMessageContent message={userMessage("**bold** text")} />,
    );

    expect(getByText("bold")).toBeOnTheScreen();
    expect(queryByText("**bold** text")).toBeNull();
  });

  it("still renders plain prose with no markdown syntax unchanged", async () => {
    const { getByText } = await render(
      <UserMessageContent message={userMessage("What time is it in Tokyo?")} />,
    );

    expect(getByText("What time is it in Tokyo?")).toBeOnTheScreen();
  });

  it("BUG FIX regression: sent bare equation does not use math draft preview (only $-delimited)", async () => {
    // Sent messages with bare equations (no $) should NOT render via
    // MathDraftPreview — they go through the normal markdown path.
    // Only $-delimited math uses the draft preview for sent messages.
    const { queryByTestId } = await render(
      <UserMessageContent message={userMessage("x^2 = 4")} />,
    );
    expect(queryByTestId("math-draft-preview")).toBeNull();
  });

  it("BUG FIX regression: sent $-delimited math still uses draft preview", async () => {
    const { getByTestId } = await render(
      <UserMessageContent message={userMessage("$x^2 = 4$")} />,
    );
    expect(getByTestId("math-draft-preview")).toBeOnTheScreen();
  });

  it("BUG FIX regression: a pasted \\[...\\] write-up is not the composer math preview", async () => {
    const { queryByTestId } = await render(
      <UserMessageContent
        message={userMessage(
          "\\[ 2x^2-7x+3=0 \\]\nFactor it:\n\\[ 2x-1=0 \\]\nor\n\\[ x-3=0 \\]",
        )}
      />,
    );
    expect(queryByTestId("math-draft-preview")).toBeNull();
  });
});

describe("UserMessageContent", () => {
  it("renders a lone letter as a normal bubble", async () => {
    const { getByText, queryByLabelText } = await render(
      <UserMessageContent message={userMessage("c")} />,
    );
    expect(getByText("c")).toBeOnTheScreen();
    expect(queryByLabelText("Quiz answer C")).toBeNull();
  });
});

describe("sent math bubble", () => {
  it("sizes to one-line math instead of the composer's fixed row", async () => {
    const { getByTestId } = await render(<UserMessageContent message={userMessage("$[4,4]$")} />);
    const style = StyleSheet.flatten(getByTestId("math-draft-preview").props.style);
    expect(style.minHeight).toBe(0);
    expect(style.marginBottom).toBe(0);
  });
});

describe("UserMessageContent attachments", () => {
  const LEASE = "ab2a7d57-f8ec-4e12-8a5d-3748cd246d73";
  const NOTES = "5c1e0f3a-9b7d-4e2a-8c6f-1d2e3f4a5b6c";
  // A sent message stores only the file's link and its text; the name is on the server's row.
  const names: Record<string, string> = { [LEASE]: "lease-notes.pdf", [NOTES]: "minutes.docx" };
  const named = (attachmentId?: string | null): MockIndexStatus => ({
    indexed: true,
    failed: false,
    fileName: attachmentId ? names[attachmentId] : undefined,
  });

  afterEach(() => {
    mockIndexStatus.mockImplementation(() => ({ indexed: true, failed: false }));
  });

  it("names a reopened PDF from the server, not document.pdf", async () => {
    mockIndexStatus.mockImplementation(named);
    const content = `What is the code?\n\n[File: /attachments/${LEASE}/file]\n[File (application/pdf)]\n[page 1] The code is LIME.`;
    const { findByText, queryByText } = await render(<UserMessageContent message={userMessage(content)} />);
    expect(await findByText("pdf:lease-notes.pdf")).toBeOnTheScreen();
    expect(queryByText("pdf:document.pdf")).toBeNull();
    expect(queryByText(/The code is LIME/)).toBeNull();
  });

  it("names a reopened document from the server, not its kind", async () => {
    mockIndexStatus.mockImplementation(named);
    const docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const content = `[File: /attachments/${NOTES}/file]\n[File (${docx})]\nMinutes of the meeting.`;
    const { getByText } = await render(<UserMessageContent message={userMessage(content)} />);
    expect(getByText("minutes.docx")).toBeOnTheScreen();
  });

  // Secondary ink on the bubble measured 4.07-4.48:1 in dark mode with the
  // graphite, sapphire, berry and orchid accents.
  it.each(["light", "dark"] as const)(
    "keeps a file's name AA on every accent's bubble in %s mode",
    async (scheme) => {
      mockScheme = scheme;
      mockIndexStatus.mockImplementation(named);
      const docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
      const content = `[File: /attachments/${NOTES}/file]\n[File (${docx})]\nMinutes of the meeting.`;
      try {
        for (const accent of ACCENT_OPTIONS) {
          await act(async () => setAccentSnapshot(accent));
          const { getByText, unmount } = await render(<UserMessageContent message={userMessage(content)} />);
          const name = getByText("minutes.docx");
          let plane: string | undefined;
          for (let node = name.parent; node && !plane; node = node.parent) {
            plane = StyleSheet.flatten(node.props.style)?.backgroundColor as string | undefined;
          }
          const ink = String(StyleSheet.flatten(name.props.style).color);
          expect({ accent, aa: contrastRatio(ink, String(plane)) >= AA }).toEqual({ accent, aa: true });
          await unmount();
        }
      } finally {
        mockScheme = "light";
        await act(async () => setAccentSnapshot(DEFAULT_ACCENT));
      }
    },
  );

  it("keeps the name the phone sent it with", async () => {
    mockIndexStatus.mockImplementation(named);
    const content = `[File: /attachments/${LEASE}/file]\n[File (application/pdf)]\nText.`;
    const message = { ...userMessage(content), local_file_name: "Lease 2026.pdf" };
    const { findByText } = await render(<UserMessageContent message={message} />);
    expect(await findByText("pdf:Lease 2026.pdf")).toBeOnTheScreen();
  });
});

describe("line breaks the user typed", () => {
  it("keeps two typed lines on two lines", async () => {
    const view = await render(
      <UserMessageContent
        message={userMessage("Budget range: $1,200 - $2,500\nPrimary use: Programming & development")}
      />,
    );
    // A hard break between the two: Markdown's soft break would join them with a space.
    const pieces: string[] = [];
    const walk = (node: unknown): void => {
      if (typeof node === "string") pieces.push(node);
      else if (Array.isArray(node)) node.forEach(walk);
      else if (node && typeof node === "object" && "children" in node) {
        walk((node as { children: unknown }).children);
      }
    };
    walk(view.toJSON());
    const text = pieces.join("");
    expect(text).toContain("Budget range: $1,200 - $2,500\nPrimary use: Programming & development");
  });
});

describe("UserMessageContent for a screen reader", () => {
  it("reads plain text as one element with the long-press hint", async () => {
    const { getByA11yHint } = await render(
      <UserMessageContent message={userMessage("Plan my week")} actionsHint="hold for actions" />,
    );
    expect(getByA11yHint("hold for actions").props.accessible).toBe(true);
  });

  it.each(["See [the docs](https://example.com)", "Try example.com today"])(
    "leaves text with a link open so the link is reached: %s",
    async (content) => {
      const { queryByA11yHint, getByText } = await render(
        <UserMessageContent message={userMessage(content)} actionsHint="hold for actions" />,
      );
      expect(queryByA11yHint("hold for actions")).toBeNull();
      expect(getByText(/example\.com|the docs/)).toBeOnTheScreen();
    },
  );
});

/** The style of the nearest ancestor that flexes: the item's text column. */
type TreeNode = { parent: TreeNode | null; props: { style?: unknown } };

function itemColumnStyle(node: TreeNode): { flex?: unknown; flexShrink?: unknown } | null {
  for (let at = node.parent; at; at = at.parent) {
    const style = StyleSheet.flatten(at.props.style as never) as { flex?: unknown; flexShrink?: unknown };
    if (style && "flex" in style) return style;
  }
  return null;
}

describe("UserMessageContent typed lists", () => {
  // The bubble is as wide as its text. A list item's text column with positive flex has a
  // zero basis and adds no width, so "1. dhdhd" showed as a bubble of bare numbers.
  it.each([
    ["1. dhdhd\n2. hjdjdjd", ["dhdhd", "hjdjdjd"]],
    ["- milk\n- eggs", ["milk", "eggs"]],
  ])("sizes each item of %j from its own text", async (content, items) => {
    const { getByText } = await render(<UserMessageContent message={userMessage(content)} />);
    for (const item of items) {
      // Yoga gives any positive flex a zero basis, whatever flexBasis says.
      const style = itemColumnStyle(getByText(item));
      expect(style?.flex).toBe(0);
      expect(style?.flexShrink).toBe(1);
    }
  });
});

