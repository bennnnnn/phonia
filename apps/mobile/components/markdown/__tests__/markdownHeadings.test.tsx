import { render, screen } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import "@/lib/i18n";

jest.unmock("react-i18next");
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: () => null }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({ WebPreviewCodeBlock: "WebPreviewCodeBlock" }));
jest.mock("@/components/rich/CircularClockBlock", () => ({ CircularClockBlock: "CircularClockBlock" }));
jest.mock("@/components/rich/AnswerBlock", () => ({ AnswerBlock: "AnswerBlock" }));

describe("markdown headings", () => {
  it("are headings to a screen reader, so its heading navigation can jump between sections", async () => {
    await render(
      <MarkdownContent content={"# Plan\n\n## Step one\n\nDo it.\n\n### Notes with `code`\n\nMore."} />,
    );

    const headers = screen.getAllByRole("header");
    expect(headers).toHaveLength(3);
    expect(screen.getByRole("header", { name: "Step one" })).toBeOnTheScreen();
    // Body text stays plain text.
    expect(screen.queryByRole("header", { name: "Do it." })).toBeNull();
  });

  it("leaves a heading that holds a link open, so the link can still be focused", async () => {
    await render(<MarkdownContent content={"## [Docs](https://example.com)\n\nEnd."} />);

    expect(screen.queryAllByRole("header")).toHaveLength(0);
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
