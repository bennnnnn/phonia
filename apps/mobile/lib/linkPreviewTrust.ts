/**
 * Which links in a message may show a fetched preview card.
 *
 * A preview makes the server fetch the URL, path, query and all. A URL the
 * model wrote on its own can carry the user's memory or schedule to its host
 * when injected text (a web result, a PDF) told it to, so only links the user
 * wrote or the server's own search returned qualify. Every other link is a
 * plain card that fetches nothing (`components/LinkPreviewCard.tsx`).
 */

const URL_IN_TEXT = /https?:\/\/[^\s<>"'`]+/gi;
const TRAILING_PUNCTUATION = /[.,;:!?'"\]}>]+$/;

/** One spelling per URL: normalized by URL parsing, without its #fragment (never sent). */
export function linkPreviewKey(url: string): string | null {
  try {
    const parsed = new URL(url.trim());
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
    parsed.hash = "";
    return parsed.href;
  } catch {
    return null;
  }
}

function count(text: string, char: string): number {
  return text.split(char).length - 1;
}

/** A closing ")" belongs to the URL only when the URL opened one (Wikipedia's "Foo_(bar)"). */
function trimUrlEnd(raw: string): string {
  let url = raw.replace(TRAILING_PUNCTUATION, "");
  while (url.endsWith(")") && count(url, "(") < count(url, ")")) {
    url = url.slice(0, -1).replace(TRAILING_PUNCTUATION, "");
  }
  return url;
}

/** The previewable links: every URL in the user's own words, and the reply's search sources. */
export function previewableUrls(
  userTexts: readonly (string | null | undefined)[],
  sources: readonly { url: string }[] = [],
): ReadonlySet<string> {
  const keys = new Set<string>();
  for (const text of userTexts) {
    for (const match of text?.match(URL_IN_TEXT) ?? []) {
      const key = linkPreviewKey(trimUrlEnd(match));
      if (key) keys.add(key);
    }
  }
  for (const source of sources) {
    const key = linkPreviewKey(source.url);
    if (key) keys.add(key);
  }
  return keys;
}
