import {
  faviconUrl,
  hostnameFromUrl,
  parseSearchSources,
  preferDistinctHostSources,
  searchSourcesFromField,
  stripSearchSourcesFromContent,
} from "@/lib/searchSources";

describe("searchSources", () => {
  it("parses sources fence", () => {
    const content = `Here is the answer.

\`\`\`sources
[{"title":"AP News","url":"https://apnews.com/a","snippet":"Story text."}]
\`\`\``;
    expect(parseSearchSources(content)).toEqual([
      {
        title: "AP News",
        url: "https://apnews.com/a",
        snippet: "Story text.",
      },
    ]);
    expect(stripSearchSourcesFromContent(content)).toBe("Here is the answer.");
  });

  it("returns empty when fence missing", () => {
    expect(parseSearchSources("hello")).toEqual([]);
  });

    it("does not strip a trailing title/url JSON array that is real content", () => {
    const content = `Here is the config you asked for.

\`\`\`json
[{"title":"Home","url":"/home"},{"title":"Docs","url":"/docs"}]
\`\`\``;
    expect(stripSearchSourcesFromContent(content)).toContain('"title":"Home"');
    expect(parseSearchSources(content)).toEqual([]);
  });

  it("does not treat trailing bare title/url JSON as sources", () => {
    const content = `Here is the answer.

[{"title":"AP News","url":"https://apnews.com/a","snippet":"Story text."}]`;
    expect(parseSearchSources(content)).toEqual([]);
    expect(stripSearchSourcesFromContent(content)).toContain("AP News");
  });

  it("strips bare code fences and a sources label around JSON", () => {
    const content = `It's afternoon there.

**sources**
\`\`\`
[{"title":"Current Time in Washington, D.C.","url":"http://www.timeandzone.com/dc"}]
\`\`\``;
    expect(parseSearchSources(content)).toEqual([
      {
        title: "Current Time in Washington, D.C.",
        url: "http://www.timeandzone.com/dc",
      },
    ]);
    expect(stripSearchSourcesFromContent(content)).toBe("It's afternoon there.");
  });

  it("does not hang when content starts with an unparseable '[' (e.g. an image marker)", () => {
    // Regression: lastIndexOf("[", -1) clamps to 0 instead of returning -1,
    // so the old loop re-found the same leading "[" forever once it reached
    // index 0 without finding valid trailing JSON. Every generated-image
    // reply is exactly this shape ("[Image: /attachments/<id>/file]"), so
    // this previously froze the JS thread on every image generation.
    const content = "[Image: /attachments/11111111-1111-1111-1111-111111111111/file]";
    expect(parseSearchSources(content)).toEqual([]);
    expect(stripSearchSourcesFromContent(content)).toBe(content);
  }, 2000);

  it("does not hang on other unparseable leading-bracket content", () => {
    expect(parseSearchSources("[not json at all")).toEqual([]);
    expect(parseSearchSources("[[[[[")).toEqual([]);
  }, 2000);

  it("extracts hostname", () => {
    expect(hostnameFromUrl("https://www.bbc.com/news")).toBe("bbc.com");
  });

  it("lists distinct hosts first", () => {
    expect(
      preferDistinctHostSources([
        { title: "A1", url: "https://espn.com/a" },
        { title: "A2", url: "https://espn.com/b" },
        { title: "B", url: "https://bbc.com/c" },
      ]).map((s) => s.title),
    ).toEqual(["A1", "B", "A2"]);
  });

  it("builds favicon url from host", () => {
    expect(faviconUrl("https://www.bbc.com/news")).toContain("bbc.com");
  });

  it("reads a done event's sources as JSON text or as an array", () => {
    const rows = [{ title: "AP News", url: "https://apnews.com/a", snippet: "Story text." }];
    expect(searchSourcesFromField(JSON.stringify(rows))).toEqual(rows);
    expect(searchSourcesFromField(rows)).toEqual(rows);
    expect(searchSourcesFromField([{ url: "https://apnews.com/a" }])).toEqual([
      { title: "https://apnews.com/a", url: "https://apnews.com/a" },
    ]);
    for (const absent of [undefined, null, "", "not json", { title: "x" }, 5]) {
      expect(searchSourcesFromField(absent)).toEqual([]);
    }
  });
});
