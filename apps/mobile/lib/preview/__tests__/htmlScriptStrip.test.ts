import { stripScripts } from "@/lib/preview/htmlScriptStrip";

/** base64 of `<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>`: an SVG document that runs script. */
const SVG_WITH_SCRIPT_B64 =
  "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIG9ubG9hZD0iYWxlcnQoMSkiLz4=";

describe("stripScripts", () => {
  it("strips plain <script> tags and on*= handlers (baseline, unchanged)", () => {
    const out = stripScripts('<script>alert(1)</script><div onclick="alert(2)">x</div>');
    expect(out).not.toContain("<script>");
    expect(out).not.toContain("alert(1)");
    expect(out).not.toContain("onclick");
  });

  // BUG FIX (was a confirmed bypass): "/" is a valid inter-attribute
  // separator in HTML, not just whitespace, so <svg/onload=...> fires
  // automatically on render — a well-known, real-world XSS-filter-evasion
  // technique. The old regex required literal whitespace before "on\w+".
  it("strips on*= handlers separated by '/' instead of whitespace", () => {
    const out = stripScripts('<svg/onload=alert(document.domain)>');
    expect(out).not.toContain("onload");
    expect(out).not.toContain("alert(document.domain)");
  });

  // BUG FIX (was a confirmed bypass): browsers HTML-decode an iframe's
  // srcdoc attribute before parsing it as the iframe's own document, so an
  // entity-encoded <script> inside srcdoc executes on load with zero
  // clicks. The old code only looked for the literal string "<script",
  // never inside an attribute value.
  it("strips iframe srcdoc containing an entity-encoded script", () => {
    const out = stripScripts(
      '<iframe srcdoc="&lt;script&gt;fetch(&#39;https://evil.example&#39;)&lt;/script&gt;"></iframe>',
    );
    expect(out).not.toContain("srcdoc");
  });

  it("strips javascript: URLs from href/src/action/formaction/data attributes", () => {
    const cases = [
      '<a href="javascript:alert(1)">click</a>',
      "<a href='javascript:alert(1)'>click</a>",
      '<img src="javascript:alert(1)">',
      '<form action="javascript:alert(1)"><button formaction="javascript:alert(1)">go</button></form>',
      '<object data="javascript:alert(1)"></object>',
    ];
    for (const html of cases) {
      const out = stripScripts(html);
      expect(out.toLowerCase()).not.toContain("javascript:");
    }
  });

  it("strips javascript: URLs obfuscated with embedded whitespace/control characters", () => {
    const out = stripScripts('<a href="java\tscript:alert(1)">click</a>');
    expect(out.toLowerCase()).not.toContain("javascript:");
  });

  it("strips vbscript: URLs", () => {
    const out = stripScripts('<a href="vbscript:msgbox(1)">click</a>');
    expect(out.toLowerCase()).not.toContain("vbscript:");
  });

  it("disarms zero-click meta-refresh redirects", () => {
    const out = stripScripts(
      '<meta http-equiv="refresh" content="0;url=https://evil.example/phish">',
    );
    // Renamed, not removed (lib/preview/htmlMetaPragmas.ts): no pragma is left to act.
    expect(out).toBe('<meta data-blocked-http-equiv="refresh" content="0;url=https://evil.example/phish">');
  });

  it("leaves ordinary safe links and images untouched", () => {
    const out = stripScripts(
      '<a href="https://example.com">link</a><img src="https://example.com/x.png"><img src="data:image/png;base64,AAAA">',
    );
    expect(out).toContain('href="https://example.com"');
    expect(out).toContain('src="https://example.com/x.png"');
    expect(out).toContain('src="data:image/png;base64,AAAA"');
  });

  it("strips data:text/html URLs while keeping data:image", () => {
    const out = stripScripts(
      '<a href="data:text/html,<script>alert(1)</script>">x</a><img src="data:image/png;base64,AAAA">',
    );
    expect(out.toLowerCase()).not.toContain("data:text/html");
    expect(out).toContain('src="data:image/png;base64,AAAA"');
  });

  it("strips script end tags with junk before >", () => {
    const out = stripScripts("<script>alert(1)</script\t\n bar><p>ok</p>");
    expect(out.toLowerCase()).not.toContain("alert");
    expect(out).toContain("<p>ok</p>");
  });
});

// A3 (HTML export): each of these got through stripScripts on main, so the
// document "Open in browser" / Share handed over still carried a live script
// URL or handler. `gone` is what must not survive.
const BYPASSES: { name: string; html: string; gone: RegExp }[] = [
  // Character references a browser decodes before it follows the URL.
  { name: "decimal reference", html: '<a href="&#106;avascript:alert(1)">x</a>', gone: /href|avascript/i },
  { name: "decimal, no semicolon", html: '<a href="&#106avascript:alert(1)">x</a>', gone: /href|avascript/i },
  { name: "padded decimal", html: '<a href="&#0000106;avascript:alert(1)">x</a>', gone: /href|avascript/i },
  { name: "hex reference", html: '<a href="&#x6A;avascript:alert(1)">x</a>', gone: /href|avascript/i },
  { name: "upper-case hex", html: '<a href="&#X6A;AVASCRIPT:alert(1)">x</a>', gone: /href|avascript/i },
  { name: "&colon;", html: '<a href="javascript&colon;alert(1)">x</a>', gone: /href|javascript/i },
  { name: "tab reference", html: '<a href="jav&#x09;ascript:alert(1)">x</a>', gone: /href|ascript/i },
  { name: "&Tab;", html: '<a href="jav&Tab;ascript:alert(1)">x</a>', gone: /href|ascript/i },
  { name: "&NewLine;", html: '<a href="jav&NewLine;ascript:alert(1)">x</a>', gone: /href|ascript/i },
  { name: "every letter encoded", html: '<a href="&#x6a;&#x61;&#x76;&#x61;&#x73;&#x63;&#x72;&#x69;&#x70;&#x74;&#x3a;alert(1)">x</a>', gone: /href|alert/i },
  { name: "encoded data:text/html", html: '<iframe src="data&colon;text&sol;html,&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>', gone: /src=|alert/i },
  { name: "encoded vbscript:", html: '<a href="vbscript&#58;msgbox(1)">x</a>', gone: /href|msgbox/i },
  // SVG links and the documents SVG loads.
  { name: "svg xlink:href", html: '<svg><a xlink:href="javascript:alert(1)"><text y="20">x</text></a></svg>', gone: /href|javascript/i },
  { name: "svg XLINK:HREF, encoded", html: '<svg><a XLINK:HREF="&#106;avascript:alert(1)"><text y="20">x</text></a></svg>', gone: /href|avascript/i },
  { name: "svg use data:image/svg+xml", html: `<svg><use xlink:href="data:image/svg+xml;base64,${SVG_WITH_SCRIPT_B64}#x"/></svg>`, gone: /href|data:/i },
  { name: "svg use data:text/html", html: '<svg><use href="data:text/html,<svg id=x onload=alert(1)>#x"/></svg>', gone: /href|alert/i },
  { name: "svg animate values", html: '<svg><a><animate attributeName="href" values="#;javascript:alert(1)"/><text y="20">x</text></a></svg>', gone: /values|javascript/i },
  { name: "svg set to", html: '<svg><a><set attributeName="href" to="javascript:alert(1)"/><text y="20">x</text></a></svg>', gone: /\sto=|javascript/i },
  { name: "iframe svg document", html: `<iframe src="data:image/svg+xml;base64,${SVG_WITH_SCRIPT_B64}"></iframe>`, gone: /src=|svg\+xml/i },
  { name: "embed svg document", html: `<embed src="data:image/svg+xml;base64,${SVG_WITH_SCRIPT_B64}">`, gone: /src=|svg\+xml/i },
  { name: "object svg document", html: `<object data="data:image/svg+xml;base64,${SVG_WITH_SCRIPT_B64}"></object>`, gone: /data=|svg\+xml/i },
  // Case, whitespace and control characters.
  { name: "upper-case scheme and name", html: '<A HREF="JaVaScRiPt:alert(1)">x</A>', gone: /href|javascript/i },
  { name: "leading spaces and controls", html: '<a href="  \u0001\u001f javascript:alert(1)">x</a>', gone: /href|javascript/i },
  { name: "newline inside the scheme", html: '<a href="java\nscript:alert(1)">x</a>', gone: /href|script:/i },
  { name: "unquoted value", html: "<a href=javascript:alert(1)>x</a>", gone: /href|javascript/i },
  { name: "spaces around =", html: '<a href \n=\t "javascript:alert(1)">x</a>', gone: /href|javascript/i },
  // Separators other than whitespace start an attribute too.
  { name: "slash before href", html: '<a/href="javascript:alert(1)">x</a>', gone: /href|javascript/i },
  { name: "no space after a quoted value", html: '<a title="t"href="javascript:alert(1)">x</a>', gone: /href|javascript/i },
  { name: "handler after a quoted value", html: '<img src="x"onerror="alert(1)">', gone: /onerror|alert/i },
  { name: "handlers back to back", html: "<img src=\"x\"onerror=\"alert(1)\"onload='alert(2)'>", gone: /onerror|onload|alert/i },
  { name: "slash before srcdoc", html: '<iframe/srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>', gone: /srcdoc|alert/i },
  { name: "unquoted srcdoc", html: "<iframe srcdoc=&lt;script&gt;alert(1)&lt;/script&gt;></iframe>", gone: /srcdoc|alert/i },
  // List-valued URL attributes are checked entry by entry.
  { name: "srcset second entry", html: '<img srcset="a.png 1x, javascript:alert(1) 2x">', gone: /srcset|javascript/i },
  { name: "poster", html: '<video poster="javascript:alert(1)"></video>', gone: /poster|javascript/i },
  { name: "background", html: '<table background="javascript:alert(1)"></table>', gone: /background|javascript/i },
  // A removal must not assemble new markup from the pieces either side.
  { name: "script assembled by removing a handler", html: '<scr onx="y"ipt>alert(1)</script>', gone: /<script/i },
  { name: "script assembled by removing a URL", html: '<scr href="javascript:x"ipt>alert(1)</script>', gone: /<script/i },
  { name: "script assembled by removing a refresh", html: "<scr<meta http-equiv=refresh content=0>ipt>alert(1)</script>", gone: /<script/i },
  { name: "handler assembled by removing a URL", html: '<a onclick href="javascript:x"=alert(1)>x</a>', gone: /onclick/i },
];

describe("stripScripts: bypass classes (A3)", () => {
  it.each(BYPASSES)("neutralises $name", ({ html, gone }) => {
    expect(stripScripts(html)).not.toMatch(gone);
  });

  it("keeps the markup around a removed attribute", () => {
    expect(stripScripts('<a class="c" href="&#106;avascript:alert(1)" title="t">x</a>')).toBe(
      '<a class="c"   title="t">x</a>',
    );
  });

  it("keeps safe URLs, raster data images and references that decode to them", () => {
    const safe = [
      '<a href="https://example.com/?a=1&amp;b=2">x</a>',
      '<a href="#top">x</a>',
      '<a href="mailto:me@example.com">x</a>',
      '<a href="/javascript-guide">x</a>',
      '<img srcset="a.png 1x, data:image/png;base64,AAAA 2x">',
      '<img src="DATA:IMAGE/PNG;base64,AAAA">',
      '<svg><a xlink:href="#target"><text>x</text></a></svg>',
      '<svg><animate attributeName="x" from="0" to="10" dur="1s"/></svg>',
      '<a data-src="javascript:void(0)">x</a>',
      '<a href="https://example.com/&#106;s">x</a>',
    ];
    for (const html of safe) expect(stripScripts(html)).toBe(html);
  });

  it("returns input that keeps producing new markup as escaped text", () => {
    // Each level's handler and URL only become attributes once the level inside
    // is removed, one more pass per level.
    const nested = (levels: number) => {
      let attrs = ' href="javascript:0"';
      for (let i = 1; i <= levels; i++) attrs = ` href on${i}${attrs}=v${i} ="javascript:${i}"`;
      return `<a${attrs}>x</a>`;
    };
    const shallow = stripScripts(nested(10));
    expect(shallow).toMatch(/^<a\s+>x<\/a>$/);
    // More levels than passes allowed: nothing comes back as markup.
    const deep = stripScripts(nested(40));
    expect(deep).not.toMatch(/<a/);
    expect(deep).toContain("&lt;a");
  });
});
