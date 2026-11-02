/**
 * Whether a composer send might be a picture or a photo lookup, so the server is
 * worth asking (`POST /images/intent`). Only the server reads image intent: this
 * decides nothing but the round trip. A false positive costs one request; a miss
 * would send a picture request as plain chat, so the words come from the server's
 * own lists (apps/api/app/modules/images/gen_intent_words.py, lookup_intent.py and
 * intent.py), and the test runs every case the server draws or looks up.
 */

import {
  IMAGE_GEN_FAILED_ASSISTANT_ID,
  IMAGE_GEN_PENDING_ASSISTANT_ID,
} from "@/features/images/model/imageGenMessages";

type Row = { id: string; role: string; content: string };

/**
 * Word starts the server's readers need: the drawing verbs and picture nouns
 * ("pic" covers pics and pictures), and the photo lookup's "show", "see" and
 * "look like". A word starts after anything but a letter, digit or underscore.
 */
const IMAGE_WORDS =
  /(?:^|[^a-z0-9_])(?:create|design|generate|make|produce|render|draw|illustrat|paint|image|photo|pic|artwork|portrait|show|see|look)/;
/**
 * The same in the app's other languages (gen_intent_languages.py): the server draws there
 * only "draw me" ("dibújame", "zeichne mir", "bana … çiz", "ድመት ሳልልኝ") and "create a
 * picture of" ("erstelle ein Bild von", "crea una ilustración de"), so these are its draw
 * verbs and picture nouns. German "mal"/"male" count only before "mir"/"uns": alone they
 * are "once" and "bad" ("Erklär mal …", "Me siento mal").
 */
const OTHER_LANGUAGE_WORDS = new RegExp(
  "(?:^|[^a-z0-9_])(?:" +
    "dibuj|dibúj|pínt|pintame|pintas|pintar|ilustrac|ilustraç|dessin|peins|peignez|peindre|illustr|" +
    "zeichn|male?\\s+(?:mir|uns)(?![a-zäöüß])|malen|bild(?![a-zäöüß])|" +
    "disegn|dipin|immagin|desenh|çiz|resm|görsel|" +
    "нарис|изобра|картинк|рисун|иллюстр|" +
    "ሳልልኝ|ሣልልኝ|ሳይልኝ|ሣይልኝ|ሳሉልኝ|ሣሉልኝ|ምስል|ስዕል|ሥዕል|ስእል)",
);
/** With an image attached, these start an edit of it ("crop it", "turn it into…"). */
const EDIT_WORDS = /(?:^|[^a-z0-9_])(?:edit|change|remove|replace|recolor|crop|transform|turn)/;
/** "do it" after a picture request: the server reads one only in a line this short. */
const SHORT_LINE = 40;
const CLOSING_PUNCTUATION = /[.!?]+$/;

function hasImageWord(text: string, imageAttached: boolean): boolean {
  const folded = text.toLowerCase();
  return IMAGE_WORDS.test(folded) || OTHER_LANGUAGE_WORDS.test(folded) ||
    (imageAttached && EDIT_WORDS.test(folded));
}

/** Whitespace to the phone or to the server (Python also splits on \x1c–\x1f and \x85). */
function isSpace(char: string): boolean {
  return /\s/.test(char) || ("\x1c" <= char && char <= "\x1f") || char === "\x85";
}

/** At most `SHORT_LINE` characters, not counting spaces or closing punctuation. */
function isShortLine(text: string): boolean {
  const kept = Array.from(text).filter((char) => !isSpace(char)).join("");
  return Array.from(kept.replace(CLOSING_PUNCTUATION, "")).length <= SHORT_LINE;
}

/** Rows the server has stored; a streaming, pending or optimistic row is the phone's alone. */
function storedRows(messages: readonly Row[]): Row[] {
  return messages.filter((row) =>
    row.id !== "streaming" &&
    row.id !== IMAGE_GEN_PENDING_ASSISTANT_ID &&
    row.id !== IMAGE_GEN_FAILED_ASSISTANT_ID &&
    !row.id.startsWith("local-"));
}

/**
 * After a picture any short line may edit it ("White"), and "do it" may confirm
 * a picture asked for just before: both need the chat, not the words.
 */
function threadInvitesImage(text: string, messages: readonly Row[]): boolean {
  const rows = storedRows(messages);
  const lastReply = [...rows].reverse().find((row) => row.role === "assistant");
  if (lastReply?.content.includes("[Image:")) return true;
  if (!isShortLine(text)) return false;
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const row = rows[i];
    if (row.role !== "user") continue;
    if (hasImageWord(row.content, false)) return true;
    if (!isShortLine(row.content)) return false;
  }
  return false;
}

/** True when the server should read this send before it goes to chat. */
export function mightBeImageTurn(
  text: string,
  messages: readonly Row[],
  imageAttached: boolean,
): boolean {
  return hasImageWord(text, imageAttached) || threadInvitesImage(text, messages);
}
