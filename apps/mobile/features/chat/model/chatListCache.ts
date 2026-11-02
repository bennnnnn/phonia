import { api, type Chat, type ChatList } from "@/lib/api";
import { getSessionGeneration, requireTokenSession } from "@/lib/auth";
import { clearKnownAssistantChats } from "@/features/chat/model/draftLogic";
import {
  allChatsFromGroups,
  appendArchivedChats,
  appendOlderChats,
  emptyChatList,
  regroupChatsByRecency,
} from "@/features/chat/model/listSections";
import {
  SessionResourceCache,
  type FailureReporter,
  type ResourceResult,
  type ResourceUpdate,
} from "@/lib/cache/sessionResource";
import { CHAT_LIST_STALE_MS } from "@/features/chat/drawer/drawerChatList";
import { scheduleIdleTask } from "@/lib/scheduleIdle";
import { tokenSubject } from "@/lib/tokenSubject";

type ListSession = {
  createdChat?: Chat;
  /** The signed-in account; the file is written for it. */
  owner?: string;
  /** The list the file holds now: read back from it, or last written to it. */
  stored?: ChatList;
  restore?: Promise<boolean>;
  saveQueued?: boolean;
};

const LIST = "chats";
const resource = new SessionResourceCache<typeof LIST, ChatList, ListSession>({
  staleMs: CHAT_LIST_STALE_MS,
  // The first chat is inserted before the first full read and must not count as one.
  empty: emptyChatList,
  sessionState: () => ({}),
});
resource.subscribe(saveSoon);

/** The file layer loads expo-file-system: only a restore or a write needs it. */
const listFile = () => import("@/features/chat/model/chatListFile");

/** The account a token of this session belongs to; null for a token another session holds. */
function ownerOf(token: string): string | null {
  try {
    requireTokenSession(token);
  } catch {
    return null;
  }
  const owner = tokenSubject(token);
  if (owner) resource.state().owner ??= owner;
  return owner;
}

/**
 * Write the list to disk once the phone is idle, for a cold start to paint: a
 * list this session read, or restored and then edited. A list that only holds
 * edits made before any read is not the account's list and is never written.
 */
function saveSoon(): void {
  const state = resource.state();
  if (state.saveQueued) return;
  state.saveQueued = true;
  const current = resource.lease();
  scheduleIdleTask(() => {
    state.saveQueued = false;
    const list = resource.get(LIST);
    if (!current() || !state.owner || !list || list === state.stored) return;
    if (resource.fetchedAt(LIST) === undefined && state.stored === undefined) return;
    state.stored = list;
    const owner = state.owner;
    void listFile().then((file) => file.writeStoredChatList(owner, list)).catch(() => {});
  });
}

/**
 * Show the chats this account had last time while the drawer reads them again:
 * a cold start paints the drawer at once. The restored list is never fresh, so
 * that read still happens, and it never replaces one already read or edited.
 */
export function restoreChatList(token: string): Promise<boolean> {
  const owner = ownerOf(token);
  if (!owner) return Promise.resolve(false);
  const state = resource.state();
  state.restore ??= (async () => {
    const session = getSessionGeneration();
    const current = resource.lease();
    const list = await listFile().then((file) => file.readStoredChatList(owner)).catch(() => null);
    if (!list || !current() || !resource.seed(LIST, list, session)) return false;
    state.stored = list;
    return true;
  })();
  return state.restore;
}

/** POST /chats body — first reply inserts the drawer row without GET /chats/{id}. */
export function rememberCreatedChat(chat: Chat): void {
  resource.state().createdChat = chat;
}

export function peekCreatedChat(id: string): Chat | undefined {
  const chat = resource.state().createdChat;
  return chat?.id === id ? chat : undefined;
}

export function getCachedChatList(): ChatList | undefined {
  return resource.get(LIST);
}

/**
 * The cached list with each dated chat under the heading it has now, in the phone's
 * zone (`regroupChatsByRecency`): a list restored from disk or held across midnight.
 * An edit, so a read running now and the disk copy keep it too.
 */
export function regroupCachedChatList(): ChatList | undefined {
  const list = resource.get(LIST);
  if (!list || regroupChatsByRecency(list) === list) return list;
  return resource.update(LIST, (current) => regroupChatsByRecency(current));
}

/** Drawer row already has title / pin / class id — skip GET /chats/{id}. */
export function getCachedChat(id: string): Chat | undefined {
  const list = getCachedChatList();
  return list ? allChatsFromGroups(list).find((chat) => chat.id === id) : undefined;
}

/**
 * The drawer row as the server sent it this session. A list restored from disk
 * paints the drawer, but its titles may predate a rename on another device.
 */
export function getFetchedChat(id: string): Chat | undefined {
  return getChatListFetchedAt() != null ? getCachedChat(id) : undefined;
}

export function getChatListFetchedAt(): number | undefined {
  return resource.fetchedAt(LIST);
}

export function isChatListFresh(): boolean {
  return resource.isFresh(LIST);
}

export function setChatListCache(data: ChatList): void {
  resource.set(LIST, data);
}

/** Replay edits over an already-running read so it cannot restore a deleted/old row. */
export function updateChatListCache(update: ResourceUpdate<ChatList>): ChatList {
  return resource.update(LIST, update) ?? emptyChatList();
}

/** Sign-out, or a change to many chats at once: forget the list, on disk too. */
export function invalidateChatListCache(): Promise<void> {
  resource.invalidate();
  clearKnownAssistantChats();
  return listFile().then((file) => file.clearStoredChatList()).catch(() => {});
}

export async function fetchChatList(
  token: string,
  opts?: { force?: boolean; report?: FailureReporter },
): Promise<ResourceResult<ChatList>> {
  const result = await resource.fetch(LIST, token, async () => {
    const data = await api.listChats(token);
    return { ...data, archived: data.archived ?? [] };
  }, opts);
  if (!result.error) ownerOf(token);
  return result;
}

/**
 * Read the next page of older dated chats into the cached list; null when there is none.
 * A refresh that landed meanwhile changed the cursor, and the page is dropped.
 */
export async function fetchOlderChats(token: string): Promise<ChatList | null> {
  const cursor = getCachedChatList()?.next_cursor;
  if (!cursor) return null;
  const session = getSessionGeneration();
  const older = await api.listOlderChats(token, cursor);
  // Another account signed in meanwhile: the page is not theirs.
  return resource.update(LIST, (current) =>
    current.next_cursor === cursor ? appendOlderChats(current, older) : current, session) ?? null;
}

/**
 * Read the next page of archived chats into the cached list; null when there is none.
 * Past the drawer's first page they were out of reach (only the newest 50 were listed).
 */
export async function fetchMoreArchivedChats(token: string): Promise<ChatList | null> {
  const cursor = getCachedChatList()?.archived_next_cursor;
  if (!cursor) return null;
  const session = getSessionGeneration();
  const page = await api.listArchivedChats(token, cursor);
  return resource.update(LIST, (current) =>
    current.archived_next_cursor === cursor ? appendArchivedChats(current, page) : current, session) ?? null;
}
