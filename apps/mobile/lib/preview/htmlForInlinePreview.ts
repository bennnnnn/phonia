function isTagNameEnd(ch: string): boolean {
  // Tag name continues through letters/digits/hyphen/colon; anything else ends it.
  if (!ch) return true;
  const code = ch.charCodeAt(0);
  return !(
    (code >= 65 && code <= 90) ||
    (code >= 97 && code <= 122) ||
    (code >= 48 && code <= 57) ||
    ch === "-" ||
    ch === ":"
  );
}

/**
 * Strip matched `<tag>...</tag>` (and self-closing) regions with index scanning.
 * Avoids regex `.replace` that CodeQL flags as incomplete multi-character sanitization.
 */
function removeTagBlocks(html: string, tag: string): string {
  const open = `<${tag}`;
  const close = `</${tag}`;
  let out = html;
  let searchFrom = 0;
  for (let guard = 0; guard < 64; guard++) {
    const lower = out.toLowerCase();
    const start = lower.indexOf(open, searchFrom);
    if (start === -1) break;
    if (!isTagNameEnd(lower.charAt(start + open.length))) {
      searchFrom = start + open.length;
      continue;
    }
    const openGt = out.indexOf(">", start);
    if (openGt === -1) {
      out = out.slice(0, start);
      break;
    }
    if (out.charAt(openGt - 1) === "/") {
      out = out.slice(0, start) + out.slice(openGt + 1);
      // Restart: stitching can form a new opener earlier (e.g. <scr<script>).
      searchFrom = 0;
      continue;
    }
    const closeStart = lower.indexOf(close, openGt + 1);
    if (closeStart === -1) {
      out = out.slice(0, start) + out.slice(openGt + 1);
      searchFrom = 0;
      continue;
    }
    if (!isTagNameEnd(lower.charAt(closeStart + close.length))) {
      // Rare: `</stylesheet` etc. — skip this close and keep looking.
      searchFrom = closeStart + close.length;
      continue;
    }
    const closeGt = out.indexOf(">", closeStart);
    if (closeGt === -1) {
      out = out.slice(0, start);
      break;
    }
    out = out.slice(0, start) + out.slice(closeGt + 1);
    searchFrom = 0;
  }
  return out;
}

/** Drop every `<…>` span for visible-text detection (index scan, not regex). */
function textWithoutTags(html: string): string {
  let out = "";
  let i = 0;
  while (i < html.length) {
    const lt = html.indexOf("<", i);
    if (lt === -1) {
      out += html.slice(i);
      break;
    }
    out += html.slice(i, lt);
    const gt = html.indexOf(">", lt + 1);
    if (gt === -1) break;
    i = gt + 1;
  }
  return out;
}

function hasImgTag(html: string): boolean {
  const lower = html.toLowerCase();
  let from = 0;
  while (from < lower.length) {
    const idx = lower.indexOf("<img", from);
    if (idx === -1) return false;
    if (isTagNameEnd(lower.charAt(idx + 4))) return true;
    from = idx + 4;
  }
  return false;
}

function extractBodyInner(html: string): string | null {
  const lower = html.toLowerCase();
  const bodyOpen = lower.indexOf("<body");
  if (bodyOpen === -1) return null;
  if (!isTagNameEnd(lower.charAt(bodyOpen + 5))) return null;
  const bodyGt = html.indexOf(">", bodyOpen);
  if (bodyGt === -1) return null;
  const bodyClose = lower.lastIndexOf("</body");
  if (bodyClose > bodyGt && isTagNameEnd(lower.charAt(bodyClose + 7))) {
    return html.slice(bodyGt + 1, bodyClose).trim();
  }
  return html.slice(bodyGt + 1).trim();
}

/** Strip the document shell (doctype/html/head/body) and remove style/script blocks. */
function extractVisibleInner(html: string): string {
  const trimmed = html.trim();
  if (!trimmed) return "";

  let inner = trimmed;
  const lowerTrimmed = trimmed.toLowerCase();
  const looksLikeDocument =
    lowerTrimmed.startsWith("<!doctype") || lowerTrimmed.startsWith("<html");

  if (looksLikeDocument) {
    const bodyInner = extractBodyInner(trimmed);
    if (bodyInner !== null) {
      inner = bodyInner;
    } else {
      inner = removeTagBlocks(trimmed, "head");
      // Drop remaining document shell tokens (not script/style — those use index scan).
      inner = inner
        .replace(/<!DOCTYPE[^>]*>/gi, "")
        .replace(/<\/?html[^>]*>/gi, "")
        .replace(/<\/?body[^>]*>/gi, "")
        .trim();
    }
  }

  inner = removeTagBlocks(inner, "style");
  inner = removeTagBlocks(inner, "script");
  return inner;
}

/**
 * A lone decorative glyph (icon font ligature, emoji bullet) left over after
 * stripping <style>/<script> should NOT count as "this page has content" —
 * that reads as a render, not the blank/near-blank page it actually is. Require
 * at least one real letter/digit.
 */
function hasMeaningfulVisibleText(inner: string): boolean {
  return /\p{L}|\p{N}/u.test(textWithoutTags(inner));
}

/** Strip document shell and return markup react-native-render-html can display. */
export function htmlForInlinePreview(html: string): string {
  if (!html.trim()) return "<p><strong>(empty)</strong></p>";

  const inner = extractVisibleInner(html);
  if (!hasMeaningfulVisibleText(inner) && !hasImgTag(inner)) {
    // Never dump raw CSS/HTML source into the Run tab — that reads as a bug.
    return (
      "<p><strong>This page needs a live browser preview.</strong></p>" +
      "<p>It is mostly CSS/JavaScript, so the static preview has nothing to show. " +
      "Use <strong>Share</strong> to open it, or run a dev build for in-app Run.</p>"
    );
  }

  return `<div>${inner}</div>`;
}
