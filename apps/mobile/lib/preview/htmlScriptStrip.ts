import { decodeAttributeEntities } from "@/lib/preview/htmlEntities";
import { disarmMetaPragmas } from "@/lib/preview/htmlMetaPragmas";
import { isInlineRasterDataUrl } from "@/lib/images/inlineRaster";

// Strips script from model-written HTML before it leaves the app's sandbox
// (system browser, share sheet) or reaches the Expo Go static renderer.

/**
 * What a removed construct leaves behind: one space, so the text either side
 * cannot fuse into new markup (`<scr onx="1"ipt>` must not become `<script>`).
 */
const REMOVED = " ";
/** Strip passes before giving up on input that keeps producing new markup. */
const MAX_STRIP_PASSES = 32;

const SCRIPT_BLOCK_RE = new RegExp(
  String.raw`<\s*script\b[^>]*>[\s\S]*?<\s*\/\s*script[^>]*>`,
  "gi",
);
const SCRIPT_SELF_CLOSE_RE = /<\s*script\b[^>]*\/>/gi;

/**
 * One attribute named `name`, as a browser's tokenizer finds it. It starts
 * after whitespace, `/` or the closing quote of the attribute before it
 * (`<svg/onload=…>` and `<img src="x"onerror=…>` both carry a handler); names
 * are case-insensitive. The value is quoted, or unquoted up to whitespace, `>`
 * or a quote: a quote never starts a URL scheme, and stopping there keeps the
 * closing quote of an enclosing value in place. Groups: start, name, value.
 */
function attributePattern(name: string): RegExp {
  return new RegExp(String.raw`([\s/"'])(${name})\s*=\s*("[^"]*"|'[^']*'|[^\s>"']*)`, "gi");
}

const EVENT_HANDLER_ATTR = attributePattern(String.raw`on\w+`);
const SRCDOC_ATTR = attributePattern("srcdoc");
/**
 * Attributes a browser follows or loads as a URL, under any `prefix:` too (SVG's
 * `xlink:href`). `values`/`from`/`to`/`by` are SVG animation values, which can
 * set an `href` (`<animate attributeName="href" values="javascript:…">`).
 */
const URL_ATTR = attributePattern(
  String.raw`(?:[a-z][\w.-]*:)?(?:href|src|action|formaction|data|srcset|poster|background|values|from|to|by)`,
);
/** Of those, the ones holding several URLs: every entry is checked, not just the first. */
const URL_LIST_ATTR = /(?:^|:)(?:srcset|values|from|to|by)$/;
const SCHEME_START = /javascript:|vbscript:|data:/g;

// Whitespace and C0 control characters, built via String.fromCharCode (not a
// literal char class) so no raw control bytes live in this source file.
const CONTROL_OR_WHITESPACE = new RegExp(
  "[\\s" + Array.from({ length: 0x20 }, (_, i) => String.fromCharCode(i)).join("") + "]",
  "g",
);

/**
 * An attribute value as a browser's URL parser reads it, for a scheme check:
 * unquoted, character references decoded (`&#106;avascript:`, `javascript&colon;`,
 * `jav&Tab;ascript:`), whitespace and control characters dropped (the parser
 * drops tabs and newlines anywhere and trims the rest), lower-cased.
 */
function attributeUrl(raw: string): string {
  const quoted = raw.startsWith('"') || raw.startsWith("'");
  const value = quoted ? raw.slice(1, -1) : raw;
  return decodeAttributeEntities(value).replace(CONTROL_OR_WHITESPACE, "").toLowerCase();
}

/** A URL at `at` that runs script when followed or loaded: `javascript:`, `vbscript:`, or `data:` other than a raster image. */
function isScriptUrlAt(url: string, at: number): boolean {
  if (url.startsWith("javascript:", at) || url.startsWith("vbscript:", at)) return true;
  return url.startsWith("data:", at) && !isInlineRasterDataUrl(url, at);
}

function hasScriptUrl(name: string, url: string): boolean {
  if (!URL_LIST_ATTR.test(name)) return isScriptUrlAt(url, 0);
  return Array.from(url.matchAll(SCHEME_START)).some((match) => isScriptUrlAt(url, match.index ?? 0));
}

/** Remove each attribute `pattern` finds that `drop(name, rawValue)` rejects. */
function dropAttributes(
  html: string,
  pattern: RegExp,
  drop: (name: string, rawValue: string) => boolean,
): string {
  return html.replace(pattern, (match: string, start: string, name: string, value: string) =>
    drop(name.toLowerCase(), value) ? start + REMOVED : match,
  );
}

function stripScriptsOnce(html: string): string {
  let out = html.replace(SCRIPT_BLOCK_RE, REMOVED).replace(SCRIPT_SELF_CLOSE_RE, REMOVED);
  out = dropAttributes(out, EVENT_HANDLER_ATTR, () => true);
  // An iframe decodes srcdoc into a document of its own, so any value can hold a script.
  out = dropAttributes(out, SRCDOC_ATTR, () => true);
  return dropAttributes(out, URL_ATTR, (name, value) => hasScriptUrl(name, attributeUrl(value)));
}

/**
 * Remove `<script>` blocks, inline event handlers, `srcdoc` and script URLs
 * (`javascript:`, `vbscript:`, non-raster `data:`) from HTML, and disarm every
 * `<meta http-equiv>` (lib/preview/htmlMetaPragmas.ts).
 *
 * Used for the "Open in browser" / share paths, which hand model-generated HTML
 * to the system browser, and the Expo Go static preview. Handler, `srcdoc` and
 * URL attributes are read as a browser's tokenizer reads them: any separator,
 * any case, character references decoded. A removal can expose new markup (`<a
 * onclick href="javascript:x"=alert(1)>` leaves `onclick =alert(1)`), so the
 * passes run until nothing changes; input still changing after
 * {@link MAX_STRIP_PASSES} comes back as escaped text. Pragmas are disarmed
 * last, on the final text: a removal can join a new `<meta http-equiv>`, and
 * disarming renames rather than removes, so it joins nothing. The export also
 * carries `HTML_EXPORT_CSP` (`lib/preview/previewSandbox.ts`), which refuses every
 * script even if this misses one.
 */
export function stripScripts(html: string): string {
  let out = html;
  for (let pass = 0; pass < MAX_STRIP_PASSES; pass++) {
    const next = stripScriptsOnce(out);
    if (next === out) return disarmMetaPragmas(out);
    out = next;
  }
  return html.replace(/&/g, "&amp;").replace(/</g, "&lt;");
}
