/**
 * "Where am I?" asked as the server reads it (`is_location_question`,
 * apps/api/app/services/time_context.py). The app does not use the device's
 * location: a reply to it shows no search sources. docs/fixtures/geo_intent_cases.json
 * holds this file and the server to the same answers.
 */

/**
 * Mirrors backend `is_location_question` (apps/api/app/services/time_context.py).
 * Matched, like the server, on `collapseWs` text with curly apostrophes straightened.
 */
const LOCATION_QUESTION =
  /^(?:where am i(?: (?:at|right now|right nwo|now|currently))?\??|what(?:'s| is) my (?:current |currnet )?location(?: (?:right now|now))?\??|where(?:'s| is) my (?:current |currnet )?location(?: (?:right now|now))?\??|where(?:'re| are) we(?: (?:right now|now|currently))?\??|my (?:current |currnet )?location\??|location\??)[.!?]*$/i;

/** Zero-width marks iOS can leave in a message; the server's `collapse_ws` drops them. */
const FORMAT_CHARS = /[\u200b\u200c\u200d\ufeff\u2060]/g;

/** The server's `collapse_ws`: format marks dropped, every whitespace run one space. */
function collapseWs(text: string): string {
  return text.replace(FORMAT_CHARS, "").trim().split(/\s+/).join(" ");
}

/** The server's `straighten_apostrophes`: iOS smart punctuation types \u2019 and \u2018. */
function straightenApostrophes(text: string): string {
  return text.replace(/[\u2018\u2019]/g, "'");
}

const LOCATION_ASK_MAX_LEN = 80;
/** Written folded (letters only, no doubled letter: "current" is "curent"), or it never matches. */
const LOCATION_ASK_FOLDED = new Set([
  "whereami",
  "whereamiat",
  "whereamirightnow",
  "whereamirightnwo",
  "whereaminow",
  "whereamicurently",
  "whatsmylocation",
  "whatismylocation",
  "whatsmycurentlocation",
  "whatismycurentlocation",
  "wherismylocation",
  "wheresmylocation",
  "whereismylocation",
  "wherearewe",
  "wherearewenow",
  "wherearewerightnow",
  "wherearewecurently",
  "mylocation",
  "mycurentlocation",
  "location",
]);

/** Letters only, consecutive duplicates collapsed — "Where am iI" → whereami. */
function foldLocationAsk(text: string): string {
  if (text.length > LOCATION_ASK_MAX_LEN) return "";
  let out = "";
  let prev = "";
  const lower = text.toLowerCase();
  for (let i = 0; i < lower.length; i++) {
    const ch = lower[i]!;
    if (ch < "a" || ch > "z") continue;
    if (ch !== prev) {
      out += ch;
      prev = ch;
    }
  }
  return out;
}

export function isLocationQuestion(text: string): boolean {
  const cleaned = straightenApostrophes(collapseWs(text));
  if (!cleaned) return false;
  if (LOCATION_QUESTION.test(cleaned)) return true;
  return LOCATION_ASK_FOLDED.has(foldLocationAsk(cleaned));
}
