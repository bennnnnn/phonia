import { markdownItInstance } from "@/lib/markdown/parser";

describe("literal mathematical labels in prose", () => {
  it("preserves parenthesized variable names and operator shorthand", () => {
    const html = markdownItInstance.render("Draw the hypotenuse (c), radius (r), and use +/- 2.");
    expect(html).toContain("(c)");
    expect(html).toContain("(r)");
    expect(html).toContain("+/- 2");
    expect(html).not.toMatch(/[©®™]/);
  });

  it("retains explicit symbols and regular markdown formatting", () => {
    const html = markdownItInstance.render("**Copyright © 2026** and https://example.com");
    expect(html).toContain("<strong>Copyright © 2026</strong>");
    expect(html).toContain('href="https://example.com"');
  });
});
