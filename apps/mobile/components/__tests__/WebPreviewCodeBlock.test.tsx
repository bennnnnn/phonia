import { act, fireEvent, render } from "@testing-library/react-native";

import { WebPreviewCodeBlock } from "@/components/WebPreviewCodeBlock";
import { bundleHtmlPreview, type PreviewFile } from "@/lib/preview/htmlPreviewBundle";
import { HtmlPreviewFilesProvider } from "@/lib/preview/htmlPreviewFiles";
import { openHtmlInBrowser } from "@/lib/preview/openHtmlPreview";

jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});
jest.mock("@/lib/codeTokenize", () => ({
  tokenize: (code: string) => [{ text: code, color: "#111111" }],
  resolveHighlightLang: (lang: string) => lang,
}));
jest.mock("@/lib/preview/htmlPreviewBundle", () => {
  const actual = jest.requireActual("@/lib/preview/htmlPreviewBundle");
  return { ...actual, bundleHtmlPreview: jest.fn(actual.bundleHtmlPreview) };
});
jest.mock("@/lib/preview/openHtmlPreview", () => ({ openHtmlInBrowser: jest.fn(async () => undefined) }));
jest.mock("@/components/HtmlPreviewModal", () => ({ HtmlPreviewModal: () => null }));

const HTML = "<html><head></head><body><p>hi</p></body></html>";
const css = (content: string): PreviewFile[] => [
  { kind: "html", name: "index.html", content: HTML },
  { kind: "css", name: "styles.css", content },
];

function block(files: PreviewFile[]) {
  return (
    <HtmlPreviewFilesProvider files={files}>
      <WebPreviewCodeBlock code={HTML} />
    </HtmlPreviewFilesProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("WebPreviewCodeBlock", () => {
  it("bundles nothing while its sibling files stream and nobody opens it", async () => {
    const view = await render(block(css("body{}")));
    await view.rerender(block(css("body{color:red}")));
    await act(async () => {
      await Promise.resolve();
    });
    expect(bundleHtmlPreview).not.toHaveBeenCalled();
  });

  it("bundles the current siblings when the page opens in the browser", async () => {
    const view = await render(block(css("body{color:red}")));
    await fireEvent.press(view.getByLabelText("preview.open_in_browser"));
    expect(openHtmlInBrowser).toHaveBeenCalledWith(expect.stringContaining("body{color:red}"));
  });
});
