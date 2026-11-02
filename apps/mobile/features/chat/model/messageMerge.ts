import type { Message } from "@/lib/api";
import { isJsonRecord } from "@/lib/jsonFence";
import { parseUserMessageContent } from "@/lib/messageAttachments";

type OrphanFile = {
  uri: string;
  name: string | null | undefined;
  contentType: string | null | undefined;
};

/** Previews of the files this phone sent; the server's rows never carry them. */
const LOCAL_FILE_FIELDS = [
  "local_image_uri",
  "local_file_uri",
  "local_file_name",
  "local_file_content_type",
] as const;

/** JSON-like equality; null, undefined and a missing field read the same. */
function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null || b == null) return a == null && b == null;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, index) => sameValue(item, b[index]));
  }
  return isJsonRecord(a) && isJsonRecord(b) && sameFields(a, b);
}

function sameFields(a: Record<string, unknown>, b: Record<string, unknown>, skip?: string): boolean {
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (key !== skip && !sameValue(a[key], b[key])) return false;
  }
  return true;
}

/** True when `next` draws exactly like `prior`. `renderKey` is the list key, not anything drawn. */
export function drawsSame(prior: Message, next: Message): boolean {
  return prior === next || sameFields(prior, next, "renderKey");
}

/** The server's row with what only this phone holds for it: its file previews and its list key. */
function withLocalFields(row: Message, prior: Message): Message {
  const carried: Partial<Message> = {};
  for (const field of LOCAL_FILE_FIELDS) {
    if (row[field] == null && prior[field] != null) carried[field] = prior[field];
  }
  if (row.renderKey == null && prior.renderKey != null) carried.renderKey = prior.renderKey;
  return Object.keys(carried).length > 0 ? { ...row, ...carried } : row;
}

/**
 * A row the view already shows under the same id keeps its object when the
 * server's copy draws the same, so its memoized bubble does not render (and
 * parse its markdown) again.
 */
function settleRow(prior: Message | undefined, row: Message): Message {
  if (!prior) return row;
  const next = withLocalFields(row, prior);
  return drawsSame(prior, next) ? prior : next;
}

/** `previous` itself when every row kept its object: React then skips the update. */
function unlessUnchanged(previous: Message[], next: Message[]): Message[] {
  const same = next.length === previous.length && next.every((row, index) => row === previous[index]);
  return same ? previous : next;
}

/** Local previews of optimistic rows the server copy replaces under a new id. */
function orphanLocalFiles(previous: Message[], incomingIds: ReadonlySet<string>) {
  const images: string[] = [];
  const files: OrphanFile[] = [];
  for (const m of previous) {
    if (incomingIds.has(m.id) || m.role !== "user") continue;
    if (m.local_image_uri) images.push(m.local_image_uri);
    if (m.local_file_uri) {
      files.push({ uri: m.local_file_uri, name: m.local_file_name, contentType: m.local_file_content_type });
    }
  }
  return { images, files };
}

function adoptOrphanFiles(msg: Message, orphans: ReturnType<typeof orphanLocalFiles>): Message {
  if (msg.role !== "user" || (msg.local_image_uri && msg.local_file_uri)) return msg;
  const parsed = parseUserMessageContent(msg.content);
  let local_image_uri = msg.local_image_uri ?? null;
  let local_file_uri = msg.local_file_uri ?? null;
  let local_file_name = msg.local_file_name ?? null;
  let local_file_content_type = msg.local_file_content_type ?? null;
  if (!local_image_uri && parsed.images.length > 0 && orphans.images.length > 0) {
    local_image_uri = orphans.images.shift() ?? null;
  }
  if (!local_file_uri && (parsed.files.length > 0 || parsed.hasFileAttachment) && orphans.files.length > 0) {
    const file = orphans.files.shift();
    if (file) {
      local_file_uri = file.uri;
      local_file_name = local_file_name ?? file.name ?? null;
      local_file_content_type = local_file_content_type ?? file.contentType ?? null;
    }
  }
  if (local_image_uri === (msg.local_image_uri ?? null) && local_file_uri === (msg.local_file_uri ?? null)) {
    return msg;
  }
  return { ...msg, local_image_uri, local_file_uri, local_file_name, local_file_content_type };
}

/**
 * When a silent refetch replaces the message list, keep local preview URIs
 * from optimistic bubbles so sent images don't flash blur/spinner while the
 * remote attachment file loads.
 *
 * Optimistic sends use `local-*` ids; the server list uses UUIDs, so matching
 * by id alone is not enough — also transfer orphaned local URIs onto incoming
 * user messages that carry the same attachment markers, in order. Only a row
 * the view does not show yet can be that copy: one it shows already keeps its
 * own picture.
 */
export function mergeLocalAttachmentUris(
  previous: Message[],
  incoming: Message[],
): Message[] {
  if (previous.length === 0) return incoming;
  const byId = new Map(previous.map((m) => [m.id, m]));
  const incomingIds = new Set(incoming.map((m) => m.id));
  const orphans = orphanLocalFiles(previous, incomingIds);
  const merged = incoming.map((msg) => {
    const prior = byId.get(msg.id);
    return prior ? settleRow(prior, msg) : adoptOrphanFiles(msg, orphans);
  });

  // A prior turn's assistant is not proof that the current reply was saved.
  // Keep only the current turn's partial until an assistant follows the latest
  // persisted user; otherwise refetching a second turn silently drops its reply.
  const latestIncomingUser = incoming.findLastIndex((m) => m.role === "user");
  const hasCurrentAssistant = incoming
    .slice(latestIncomingUser + 1)
    .some((m) => m.role === "assistant");
  if (!hasCurrentAssistant) {
    const latestPreviousUser = previous.findLastIndex((m) => m.role === "user");
    const streamed = previous.slice(latestPreviousUser + 1).filter(
      (m) => m.role === "assistant" && m.id.startsWith("streamed-") && !incomingIds.has(m.id),
    );
    merged.push(...streamed);
  }

  return unlessUnchanged(previous, merged);
}

/** A cached page in place of the shown thread; a repaint of the same thread keeps its local previews. */
export function paintCachedThread(previous: Message[], cached: Message[]): Message[] {
  const cachedIds = new Set(cached.map((m) => m.id));
  // Carrying local previews over only makes sense within one thread; on a chat
  // swap it could put the old chat's local image on the new chat's row.
  return previous.some((m) => cachedIds.has(m.id)) ? mergeLocalAttachmentUris(previous, cached) : cached;
}

/**
 * The chat's newest page over the thread painted from cache while it loaded.
 * `painted` is what that paint showed. Rows the view added after the last row
 * it shares with the page (a sent message, its typing dots) stay after the
 * page; a turn sent on the painted page waits for the page before it goes out
 * (openedPage.ts), so the page never holds it. Rows the view took away (a reply
 * being regenerated) stay out, and a row the page left as it was keeps its object.
 */
export function mergeOpenedPage(previous: Message[], page: Message[], painted: ReadonlySet<string>): Message[] {
  const shown = new Map(previous.map((m) => [m.id, m]));
  const pageIds = new Set(page.map((m) => m.id));
  const kept = page.filter((m) => shown.has(m.id) || !painted.has(m.id));
  const lastShared = previous.findLastIndex((m) => pageIds.has(m.id));
  const added = previous.slice(lastShared + 1).filter((m) => !painted.has(m.id));
  return unlessUnchanged(previous, [...kept.map((row) => settleRow(shown.get(row.id), row)), ...added]);
}

/**
 * True when the view shows a row that neither the cached paint nor the page
 * holds: what a turn sent while the page loaded still has on screen. With none
 * left (the turn ended unsaved) a page that turn went out before is safe to merge.
 */
export function addedSincePaint(previous: Message[], page: Message[], painted: ReadonlySet<string>): boolean {
  const pageIds = new Set(page.map((m) => m.id));
  return previous.some((m) => !painted.has(m.id) && !pageIds.has(m.id));
}
