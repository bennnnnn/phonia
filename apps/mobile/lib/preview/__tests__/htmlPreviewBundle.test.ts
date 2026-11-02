import {
  advancePreviewFilesScan,
  bundleHtmlPreview,
  fenceLangFromInfo,
  previewHasSiblingAssets,
  sanitizePreviewFilename,
} from "@/lib/preview/htmlPreviewBundle";

describe("fenceLangFromInfo", () => {
  it("reads the language and ignores a filename", () => {
    expect(fenceLangFromInfo("html index.html")).toBe("html");
    expect(fenceLangFromInfo("css styles.css")).toBe("css");
    expect(fenceLangFromInfo("javascript app.js")).toBe("javascript");
  });
});

describe("sanitizePreviewFilename", () => {
  it("accepts a basename with the right extension", () => {
    expect(sanitizePreviewFilename("styles.css", "css")).toBe("styles.css");
    expect(sanitizePreviewFilename("app.js", "js")).toBe("app.js");
  });

  it("rejects folders, traversal, and the wrong extension", () => {
    expect(sanitizePreviewFilename("../x.css", "css")).toBe("x.css");
    expect(sanitizePreviewFilename("foo/bar.css", "css")).toBe("bar.css");
    expect(sanitizePreviewFilename("styles.css", "js")).toBeNull();
    expect(sanitizePreviewFilename("nope", "css")).toBeNull();
    expect(sanitizePreviewFilename("a b.css", "css")).toBeNull();
  });
});

describe("advancePreviewFilesScan from empty", () => {
  it("collects named html/css/js siblings and skips other langs", () => {
    const md = [
      "Here is a page:",
      "",
      "```html index.html",
      "<h1>Hi</h1>",
      "```",
      "",
      "```css styles.css",
      "h1 { color: red; }",
      "```",
      "",
      "```javascript app.js",
      "console.log(1)",
      "```",
      "",
      "```python",
      "print(1)",
      "```",
    ].join("\n");
    const files = advancePreviewFilesScan(null, md).files;
    expect(files.map((f) => f.name)).toEqual(["index.html", "styles.css", "app.js"]);
    expect(previewHasSiblingAssets(files)).toBe(true);
  });

  it("assigns default names when the fence has no filename", () => {
    const md = "```html\n<p>a</p>\n```\n\n```css\nbody{}\n```\n";
    const files = advancePreviewFilesScan(null, md).files;
    expect(files.map((f) => f.name)).toEqual(["index.html", "styles.css"]);
  });
});

describe("bundleHtmlPreview", () => {
  it("returns the entry unchanged when there are no css/js siblings", () => {
    const html = "<p>solo</p>";
    expect(bundleHtmlPreview(html, [{ kind: "html", name: "index.html", content: html }])).toBe(
      html,
    );
  });

  it("inlines a linked stylesheet and script", () => {
    const html =
      '<html><head><link rel="stylesheet" href="styles.css"></head>' +
      '<body><script src="app.js"></script></body></html>';
    const out = bundleHtmlPreview(html, [
      { kind: "html", name: "index.html", content: html },
      { kind: "css", name: "styles.css", content: "h1{color:red}" },
      { kind: "js", name: "app.js", content: "window.ready=1" },
    ]);
    expect(out).toContain("<style>");
    expect(out).toContain("h1{color:red}");
    expect(out).toContain("window.ready=1");
    expect(out).not.toContain("href=\"styles.css\"");
    expect(out).not.toContain("src=\"app.js\"");
  });

  it("appends unlinked css/js so the model can omit link tags", () => {
    const html = "<html><head></head><body><h1>Hi</h1></body></html>";
    const out = bundleHtmlPreview(html, [
      { kind: "html", name: "index.html", content: html },
      { kind: "css", name: "styles.css", content: "h1{color:blue}" },
      { kind: "js", name: "app.js", content: "window.n=2" },
    ]);
    expect(out).toContain("h1{color:blue}");
    expect(out).toContain("window.n=2");
    expect(out.indexOf("h1{color:blue}")).toBeLessThan(out.indexOf("</head>"));
    expect(out.indexOf("window.n=2")).toBeLessThan(out.indexOf("</body>"));
  });

  it("does not inline a path that is not a sibling file", () => {
    const html = '<link rel="stylesheet" href="https://cdn.example/x.css">';
    const out = bundleHtmlPreview(html, [
      { kind: "html", name: "index.html", content: html },
      { kind: "css", name: "styles.css", content: "body{}" },
    ]);
    expect(out).toContain("https://cdn.example/x.css");
    expect(out).toContain("body{}");
  });
});

describe("advancePreviewFilesScan reads fences as the renderer does (audit DUP-03)", () => {
  it("leaves an html example shown inside another fence alone", () => {
    const md = "To embed a page, write:\n\n````markdown\n```html\n<p>x</p>\n```\n````\n";
    expect(advancePreviewFilesScan(null, md).files).toEqual([]);
  });

  it("reads a tilde fence", () => {
    const files = advancePreviewFilesScan(null, "~~~html\n<p>a</p>\n~~~\n").files;
    expect(files.map((f) => f.name)).toEqual(["index.html"]);
  });

  it("resumes at a code fence still streaming, so its closer is not read as an opener", () => {
    const first = advancePreviewFilesScan(null, "```html\n<p>a</p>\n```\n\n```python\nprint(1)\n");
    const done = advancePreviewFilesScan(first, `${first.source}\`\`\`\n\n\`\`\`css\nbody{}\n\`\`\`\n`);
    expect(done.files.map((f) => f.name)).toEqual(["index.html", "styles.css"]);
  });

  it("keeps a finished file while an empty preview fence opens", () => {
    const first = advancePreviewFilesScan(null, "```html\n<p>a</p>\n```\n\n```css\n");
    const next = advancePreviewFilesScan(first, `${first.source}body{}\n`);
    expect(next.files.map((f) => f.name)).toEqual(["index.html", "styles.css"]);
  });
});

describe("advancePreviewFilesScan read flush by flush", () => {
  const page = [
    "Here is the page.",
    "",
    "```html index.html",
    '<link rel="stylesheet" href="styles.css">',
    "<p>Hi</p>",
    "```",
    "",
    "```css styles.css",
    "p { color: red; }",
    "```",
    "",
    "```python",
    "print(1)",
    "```",
    "",
    "```javascript app.js",
    "console.log(1)",
    "```",
    "",
    "Open it in the preview.",
  ].join("\n");

  it("finds what one scan of the whole reply finds, wherever a flush ends", () => {
    // A flush that ended inside a fence's opener line ("``" then "`html") resumed
    // after it and never saw the fence: no files, and none once the reply settled.
    const whole = advancePreviewFilesScan(null, page).files;
    expect(whole.map((f) => f.name)).toEqual(["index.html", "styles.css", "app.js"]);
    for (let step = 1; step <= 32; step += 1) {
      let scan = advancePreviewFilesScan(null, "");
      for (let end = step; end < page.length + step; end += step) {
        scan = advancePreviewFilesScan(scan, page.slice(0, Math.min(end, page.length)));
      }
      expect({ step, files: scan.files }).toEqual({ step, files: whole });
    }
  });

  it("reads a closer line again when more of it arrives", () => {
    const first = advancePreviewFilesScan(null, "```html\n<p>a</p>\n```");
    // "```" was its closer; "```python" is not, so the html fence runs on.
    const next = advancePreviewFilesScan(first, `${first.source}python\nprint(1)\n`);
    expect(next.files).toEqual(advancePreviewFilesScan(null, next.source).files);
  });
});

describe("advancePreviewFilesScan keeps its files while they do not change", () => {
  it("returns the same array while prose streams after the last fence", () => {
    const first = advancePreviewFilesScan(null, "```html\n<p>a</p>\n```\n\nThe page");
    const next = advancePreviewFilesScan(first, `${first.source} shows a heading.`);
    expect(next.source).not.toBe(first.source);
    expect(next.files).toBe(first.files);
  });

  it("keeps the array while a fence that is no preview file streams", () => {
    const first = advancePreviewFilesScan(null, "```css\nbody{}\n```\n\n```python\nprint(1)\n");
    const next = advancePreviewFilesScan(first, `${first.source}print(2)\n`);
    expect(next.files).toBe(first.files);
  });

  it("hands out a new array once a file grows", () => {
    const first = advancePreviewFilesScan(null, "```html\n<p>a</p>\n");
    const next = advancePreviewFilesScan(first, `${first.source}<p>b</p>\n`);
    expect(next.files).not.toBe(first.files);
    expect(next.files[0].content).toBe("<p>a</p>\n<p>b</p>");
  });
});
