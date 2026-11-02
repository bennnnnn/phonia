import { linkPreviewKey, previewableUrls } from "@/lib/linkPreviewTrust";

describe("previewableUrls", () => {
  it("collects the URLs the user wrote, trimmed of sentence punctuation", () => {
    const urls = previewableUrls([
      "Summarize https://news.example/a?id=7, then (see https://blog.example/b).",
      "and https://en.wikipedia.org/wiki/Habit_(psychology)!",
    ]);
    expect([...urls]).toEqual([
      "https://news.example/a?id=7",
      "https://blog.example/b",
      "https://en.wikipedia.org/wiki/Habit_(psychology)",
    ]);
  });

  it("adds the server's search sources", () => {
    const urls = previewableUrls([null], [{ url: "https://Docs.Example/guide#intro" }]);
    expect(urls.has("https://docs.example/guide")).toBe(true);
  });

  it("never includes a URL only the model wrote", () => {
    const urls = previewableUrls(["what's on my calendar?"], []);
    expect(urls.size).toBe(0);
  });
});

describe("linkPreviewKey", () => {
  it.each([
    ["https://Example.com/a#frag", "https://example.com/a"],
    ["https://example.com", "https://example.com/"],
    ["http://example.com/x", "http://example.com/x"],
    ["javascript:alert(1)", null],
    ["not a url", null],
  ])("%s → %s", (url, key) => {
    expect(linkPreviewKey(url)).toBe(key);
  });
});
