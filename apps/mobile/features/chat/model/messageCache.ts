import {
  cacheDirectory,
  deleteAsync,
  getInfoAsync,
  makeDirectoryAsync,
  readAsStringAsync,
  readDirectoryAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

import type { Message } from "@/lib/api";
import { onAppEvent } from "@/lib/appEvents";
import { getSessionGeneration } from "@/lib/auth";
import { CONTEXT_REFRESH_STALE_MS } from "@/lib/cache/contextRefresh";
import { scheduleIdleTask } from "@/lib/scheduleIdle";
import { isServerMessageId } from "@/lib/serverMessageId";
import { MESSAGE_PAGE_SIZE } from "@/features/chat/model/constants";
import { shouldSkipSilentChatRefetch } from "@/features/chat/model/foregroundRefetch";
import { drawsSame } from "@/features/chat/model/messageMerge";
import { chatPageReadAt, noteChatPageRead } from "@/features/chat/model/pageReads";

export type CachedChatPage = {
  messages: Message[];
  has_more: boolean;
  /** When the server last confirmed the page; turns this device added since do not move it. */
  cached_at: string;
};

const CACHE_DIR = `${cacheDirectory ?? ""}chat-pages/`;
/**
 * Pages kept on disk: the newest this many chats, none older than 30 days. One file
 * per chat ever opened grew for years (code-health audit LEAK-07).
 */
const MAX_CACHED_CHATS = 100;
const MAX_CACHED_AGE_MS = 30 * 24 * 60 * 60_000;
let swept = false;
let diskWrites: Promise<void> = Promise.resolve();
let clearGeneration = 0;
const chatClearGenerations = new Map<string, number>();

/** A page this session kept for a chat it showed: painted at once on reopen, without a read while fresh. */
type KeptPage = {
  session: number;
  page: CachedChatPage;
  writtenAt: number;
  /** Something suggests the server moved on: a turn started, or the app went to the background after the read. */
  stale: boolean;
  /** The drawer row's `updated_at` when kept; a different one later means the chat changed elsewhere. */
  chatUpdatedAt: string | undefined;
};

/** The chats opened lately, the most recently kept last. */
const keptPages = new Map<string, KeptPage>();
const MAX_KEPT_PAGES = 12;
/** Chats whose kept page waits for an idle moment to reach the file. */
const unsavedChats = new Set<string>();
let cancelSave: (() => void) | null = null;
/** When the app last went to the background: a page read before it may miss another device's turns. */
let backgroundAt = 0;

function cacheIsCurrent(chatId: string): () => boolean {
  const session = getSessionGeneration();
  const all = clearGeneration;
  const chat = chatClearGenerations.get(chatId);
  return () => session === getSessionGeneration() && all === clearGeneration &&
    chat === chatClearGenerations.get(chatId);
}

// A delete must run after an already-started write. Patches share this queue so
// their read-modify-write cannot overwrite a newer page fetched from the server.
function mutateDisk(mutation: () => Promise<void>): Promise<void> {
  diskWrites = diskWrites.then(mutation).catch(() => { /* best-effort cache */ });
  return diskWrites;
}

function cachePath(chatId: string): string {
  return `${CACHE_DIR}${chatId}.json`;
}

async function ensureDir(): Promise<void> {
  if (!cacheDirectory) return;
  const info = await getInfoAsync(CACHE_DIR);
  if (!info.exists) {
    await makeDirectoryAsync(CACHE_DIR, { intermediates: true });
  }
}

export function cachedChatPageFetchedAt(
  cached: Pick<CachedChatPage, "cached_at"> | null | undefined,
): number | undefined {
  if (!cached?.cached_at) return undefined;
  const at = Date.parse(cached.cached_at);
  return Number.isFinite(at) ? at : undefined;
}

export async function readCachedChatMessages(chatId: string): Promise<CachedChatPage | null> {
  if (!cacheDirectory) return null;
  const isCurrent = cacheIsCurrent(chatId);
  try {
    const info = await getInfoAsync(cachePath(chatId));
    if (!info.exists) return null;
    const raw = await readAsStringAsync(cachePath(chatId));
    const parsed = JSON.parse(raw) as CachedChatPage;
    if (!isCurrent() || !Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** A row as the file holds it: the picker's copy of a sent file may be gone by the next launch. */
function diskRow(message: Message): Message {
  if (message.local_image_uri == null && message.local_file_uri == null) return message;
  const row = { ...message };
  delete row.local_image_uri;
  delete row.local_file_uri;
  return row;
}

/** Drop pages past the age limit, then all but the newest `MAX_CACHED_CHATS`. */
export async function sweepCachedChatPages(now: number = Date.now()): Promise<void> {
  if (!cacheDirectory) return;
  return mutateDisk(async () => {
    const names = await readDirectoryAsync(CACHE_DIR).catch(() => [] as string[]);
    const files = (await Promise.all(names.map(async (name) => {
      const path = `${CACHE_DIR}${name}`;
      const info = await getInfoAsync(path).catch(() => null);
      // Legacy file info reports seconds.
      return info?.exists ? { path, modifiedAt: (info.modificationTime ?? 0) * 1000 } : null;
    }))).filter((file): file is { path: string; modifiedAt: number } => file !== null)
      .sort((a, b) => b.modifiedAt - a.modifiedAt);
    const old = files.filter((file, index) => index >= MAX_CACHED_CHATS || now - file.modifiedAt > MAX_CACHED_AGE_MS);
    await Promise.allSettled(old.map((file) => deleteAsync(file.path, { idempotent: true })));
  });
}

export async function writeCachedChatMessages(
  chatId: string,
  messages: Message[],
  hasMore: boolean,
  cachedAt = new Date().toISOString(),
): Promise<void> {
  if (!cacheDirectory) return;
  // Once per run, before the first write: earlier runs' pages are bounded here.
  if (!swept) {
    swept = true;
    void sweepCachedChatPages();
  }
  const isCurrent = cacheIsCurrent(chatId);
  return mutateDisk(async () => {
    if (!isCurrent()) return;
    await ensureDir();
    if (!isCurrent()) return;
    const payload: CachedChatPage = {
      messages: messages.map(diskRow),
      has_more: hasMore,
      cached_at: cachedAt,
    };
    await writeAsStringAsync(cachePath(chatId), JSON.stringify(payload));
  });
}

export async function patchCachedChatMessage(
  chatId: string,
  messageId: string,
  patch: Partial<Message>,
): Promise<void> {
  const kept = keptPage(chatId);
  if (kept) {
    const messages = kept.page.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m));
    kept.page = { ...kept.page, messages };
  }
  if (!cacheDirectory) return;
  const isCurrent = cacheIsCurrent(chatId);
  return mutateDisk(async () => {
    if (!isCurrent()) return;
    const cached = await readCachedChatMessages(chatId);
    if (!cached || !isCurrent()) return;
    const messages = cached.messages.map((m) =>
      m.id === messageId ? { ...m, ...patch } : m,
    );
    await writeAsStringAsync(cachePath(chatId), JSON.stringify({ ...cached, messages }));
  });
}

export async function clearCachedChatMessages(chatId: string): Promise<void> {
  chatClearGenerations.set(chatId, (chatClearGenerations.get(chatId) ?? 0) + 1);
  keptPages.delete(chatId);
  unsavedChats.delete(chatId);
  if (!cacheDirectory) return;
  return mutateDisk(async () => {
    await deleteAsync(cachePath(chatId), { idempotent: true });
  });
}

// A photo or file deleted from the gallery leaves the chat that showed it.
onAppEvent("attachmentDeleted", ({ chatId }) => {
  if (chatId) void clearCachedChatMessages(chatId);
});

export async function clearAllCachedChatMessages(): Promise<void> {
  clearGeneration++;
  chatClearGenerations.clear();
  keptPages.clear();
  unsavedChats.clear();
  backgroundAt = 0;
  cancelSave?.();
  cancelSave = null;
  if (!cacheDirectory) return;
  return mutateDisk(async () => {
    const info = await getInfoAsync(CACHE_DIR);
    if (!info.exists) return;
    await deleteAsync(CACHE_DIR, { idempotent: true });
  });
}

function keptPage(chatId: string): KeptPage | undefined {
  const kept = keptPages.get(chatId);
  return kept?.session === getSessionGeneration() ? kept : undefined;
}

/** The page this session kept for the chat: a paint that needs no file read. */
export function peekCachedChatPage(chatId: string): CachedChatPage | null {
  return keptPage(chatId)?.page ?? null;
}

/**
 * A reopen may show the kept page without reading the chat when this device
 * wrote it within the stale window and nothing since suggests another device
 * wrote to the chat: the app stayed in the foreground and the drawer row's
 * `updated_at` is the one it had then.
 */
export function isCachedChatPageFresh(
  chatId: string,
  listedUpdatedAt: string | undefined,
  now = Date.now(),
): boolean {
  const kept = keptPage(chatId);
  // A clock set back makes the age negative: not fresh.
  const age = kept ? now - kept.writtenAt : -1;
  if (!kept || kept.stale || age < 0 || age >= CONTEXT_REFRESH_STALE_MS) return false;
  return kept.chatUpdatedAt === undefined || listedUpdatedAt === undefined ||
    kept.chatUpdatedAt === listedUpdatedAt;
}

/**
 * `silentRefetchChat` skips its read: the chat's newest page was read within the stale window,
 * by this sign-in (model/pageReads.ts) or into the page kept for it, which then counts as this
 * sign-in's read. `force` reads regardless.
 */
export async function shouldSkipChatPageRead(chatId: string, force?: boolean): Promise<boolean> {
  if (shouldSkipSilentChatRefetch({ lastFetchedAt: chatPageReadAt(chatId), force })) return true;
  const kept = cachedChatPageFetchedAt(peekCachedChatPage(chatId) ?? await readCachedChatMessages(chatId));
  if (kept === undefined || !shouldSkipSilentChatRefetch({ lastFetchedAt: kept, force })) return false;
  noteChatPageRead(chatId, kept);
  return true;
}

/** The thread changed in a way the kept page does not hold yet: the next open reads the chat. */
export function markCachedChatPageStale(chatId: string): void {
  const kept = keptPage(chatId);
  if (kept) kept.stale = true;
}

/** After the background another device may have written to any chat; only a later read clears that. */
export function markCachedChatPagesStale(): void {
  backgroundAt = Date.now();
  for (const kept of keptPages.values()) kept.stale = true;
}

/** Every row is one the server holds: a saved row, or a sent message its saved reply confirms. */
export function isSettledThread(messages: Message[]): boolean {
  return messages.length > 0 && messages.every((message, index) => {
    if (isServerMessageId(message.id)) return true;
    const next = messages[index + 1];
    return message.role === "user" && next?.role === "assistant" && isServerMessageId(next.id);
  });
}

/** A row as the cache holds it: no list key, and no local preview on a saved row (its server copy draws it). */
function cachedRow(message: Message): Message {
  const saved = isServerMessageId(message.id);
  const hasPreview = message.local_image_uri != null || message.local_file_uri != null ||
    message.local_file_name != null || message.local_file_content_type != null;
  if (message.renderKey === undefined && !(saved && hasPreview)) return message;
  const row = { ...message };
  delete row.renderKey;
  if (saved) {
    delete row.local_image_uri;
    delete row.local_file_uri;
    delete row.local_file_name;
    delete row.local_file_content_type;
  }
  return row;
}

/** The newest page of a thread. It starts on a saved row, so "Load earlier" has a cursor. */
function newestPage(messages: Message[]): { rows: Message[]; cut: boolean } {
  let start = Math.max(0, messages.length - MESSAGE_PAGE_SIZE);
  while (start > 0 && !isServerMessageId(messages[start].id)) start -= 1;
  return { rows: messages.slice(start).map(cachedRow), cut: start > 0 };
}

function samePage(a: CachedChatPage, b: CachedChatPage): boolean {
  return a.has_more === b.has_more && a.cached_at === b.cached_at &&
    a.messages.length === b.messages.length &&
    a.messages.every((message, index) => drawsSame(message, b.messages[index]));
}

function saveKeptPages(): void {
  cancelSave = null;
  for (const chatId of unsavedChats) {
    const page = peekCachedChatPage(chatId);
    if (page) void writeCachedChatMessages(chatId, page.messages, page.has_more, page.cached_at);
  }
  unsavedChats.clear();
}

/**
 * Keep the open chat's settled thread as its page: in memory now, in the file
 * once the phone is idle. `fetchedAt` is the server read the thread rests on;
 * one from before the last background leaves the page stale. Keeping the page
 * already held changes nothing, so reopening a chat never makes its page
 * fresher, and a thread that shows a row twice is never kept.
 */
export function keepCachedChatPage(
  chatId: string,
  messages: Message[],
  hasMoreOlder: boolean,
  fetchedAt: number,
  chatUpdatedAt?: string,
): void {
  if (new Set(messages.map((m) => m.id)).size !== messages.length) {
    markCachedChatPageStale(chatId);
    return;
  }
  const { rows, cut } = newestPage(messages);
  const page: CachedChatPage = {
    messages: rows, has_more: cut || hasMoreOlder, cached_at: new Date(fetchedAt).toISOString(),
  };
  const kept = keptPage(chatId);
  if (kept && samePage(kept.page, page)) return;
  keptPages.delete(chatId);
  keptPages.set(chatId, {
    session: getSessionGeneration(), page, writtenAt: Date.now(), stale: fetchedAt <= backgroundAt, chatUpdatedAt,
  });
  for (const id of keptPages.keys()) {
    if (keptPages.size <= MAX_KEPT_PAGES) break;
    keptPages.delete(id);
  }
  unsavedChats.add(chatId);
  cancelSave ??= scheduleIdleTask(saveKeptPages);
}
