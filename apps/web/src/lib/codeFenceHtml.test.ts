import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { codeLanguageLabel, renderFencedCodeHtml } from "./codeFenceHtml.ts";

describe("codeLanguageLabel", () => {
  it("names tagged fences and hides teaching fences", () => {
    assert.equal(codeLanguageLabel("python"), "Python");
    assert.equal(codeLanguageLabel("js"), "JavaScript");
    assert.equal(codeLanguageLabel(""), null);
    assert.equal(codeLanguageLabel("text"), null);
    assert.equal(codeLanguageLabel(undefined), null);
  });
});

describe("renderFencedCodeHtml", () => {
  it("puts the language in the corner and escapes the body", () => {
    const html = renderFencedCodeHtml('if a < b:\n    name = "john"', "python");
    assert.match(html, /^<pre><span>Python<\/span><code>/);
    assert.match(html, /a &lt; b/);
    assert.match(html, /name = &quot;john&quot;/);
  });

  it("omits the language span for a teaching fence", () => {
    const html = renderFencedCodeHtml('name = "john"', "");
    assert.equal(html.includes("<span>"), false);
    assert.match(html, /^<pre><code>/);
  });
});
