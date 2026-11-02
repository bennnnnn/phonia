import type { Chat } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { createListenerSet } from "@/lib/listenerSet";

/**
 * Screen-owned globals live on last-mounted-wins stacks. The chat screen can
 * be pushed on top of itself (Library → "open in chat" mounts a second copy
 * of the index route), and a popped instance's cleanup must not clear the
 * still-mounted instance underneath — with plain `let` slots, Back from the
 * pushed chat left the home screen's drawer / New chat / active-chat id
 * pointing at a dead component (or null).
 */
type StackEntry<T> = { owner: object; value: T };

function createInstanceStack<T>() {
  const stack: StackEntry<T>[] = [];
  return {
    /** Register `value` for this mounted instance; returns the unregister. */
    push(owner: object, value: T): () => void {
      const entry: StackEntry<T> = { owner, value };
      stack.push(entry);
      return () => {
        const i = stack.indexOf(entry);
        if (i >= 0) stack.splice(i, 1);
      };
    },
    top(): T | undefined {
      return stack.length ? stack[stack.length - 1].value : undefined;
    },
  };
}

// Shared drawer control — avoids circular imports between DrawerShell and ConversationList
const drawerControls = createInstanceStack<{ open: () => void; close: () => void; isOpen: () => boolean }>();

export function registerDrawer(open: () => void, close: () => void, isOpen: () => boolean): () => void {
  return drawerControls.push({}, { open, close, isOpen });
}

export function openDrawer() {
  drawerControls.top()?.open();
}
export function closeDrawer() {
  drawerControls.top()?.close();
}
/** The drawer is open now, covering the chat (for the chat screen, which sits outside it). */
export function isDrawerOpenGlobal(): boolean {
  return drawerControls.top()?.isOpen() ?? false;
}

// Shared "start a new chat" action — registered by the chat screen so the
// drawer can trigger it without prop drilling or fragile route params.
type StartNewChatOptions = { force?: boolean };
type StartNewChatFn = (opts?: StartNewChatOptions) => void;

const newChatHandlers = createInstanceStack<StartNewChatFn>();

export function registerNewChat(fn: StartNewChatFn): () => void {
  return newChatHandlers.push({}, fn);
}

export function startNewChatGlobal(opts?: StartNewChatOptions) {
  newChatHandlers.top()?.(opts);
}

// Selecting a title result can keep the same route/chat id. Explicitly cancel
// the previous message target even when there is no route change to observe.
const highlightClearers = createInstanceStack<() => void>();

export function registerChatHighlightClearer(clear: () => void): () => void {
  return highlightClearers.push({}, clear);
}
export function clearChatHighlightGlobal() {
  highlightClearers.top()?.();
}

/** Active chat id on the home screen — drawer deletes use this to avoid orphans. */
const activeChatIds = createInstanceStack<string | null>();

export function setActiveChatIdGlobal(chatId: string | null): () => void {
  return activeChatIds.push({}, chatId);
}

export function getActiveChatIdGlobal(): string | null {
  return activeChatIds.top() ?? null;
}

/** True when a delete batch includes the chat currently open on the home screen. */
export function deletedIncludesActiveChat(
  deletedIds: readonly string[],
  activeChatId: string | null = getActiveChatIdGlobal(),
): boolean {
  if (!activeChatId) return false;
  return deletedIds.includes(activeChatId);
}

/** Send the home screen back to a fresh chat if a delete just removed the open one. */
export function abandonActiveChatIfDeleted(deletedIds: readonly string[]) {
  if (!deletedIncludesActiveChat(deletedIds)) return;
  startNewChatGlobal({ force: true });
}

/** Patch a chat row in the drawer list (e.g. when auto-title arrives). */
type ChatListPatch = Partial<Chat>;

const chatPatchers = createInstanceStack<(chatId: string, patch: ChatListPatch) => void>();

export function registerChatPatcher(
  fn: (chatId: string, patch: ChatListPatch) => void,
): () => void {
  return chatPatchers.push({}, fn);
}

export function patchChatGlobal(chatId: string, patch: ChatListPatch) {
  chatPatchers.top()?.(chatId, patch);
}

/** Insert a chat into the drawer list after the first reply (see insertChatIntoGroups). */
const chatInserters = createInstanceStack<(chat: Chat) => void>();

export function registerChatInserter(fn: (chat: Chat) => void): () => void {
  return chatInserters.push({}, fn);
}

export function insertChatGlobal(chat: Chat) {
  chatInserters.top()?.(chat);
}

const chatRemovers = createInstanceStack<(chatId: string) => void>();

export function registerChatRemover(fn: (chatId: string) => void): () => void {
  return chatRemovers.push({}, fn);
}

export function removeChatGlobal(chatId: string) {
  chatRemovers.top()?.(chatId);
}

const _pendingTitleChatIds = new Set<string>();
let _onTitlePendingChange: (() => void) | null = null;

/** Mark a chat as waiting for auto-title (header + drawer show "Generating…"). */
export function setChatTitleGenerating(chatId: string | null) {
  _pendingTitleChatIds.clear();
  if (chatId) _pendingTitleChatIds.add(chatId);
  _onTitlePendingChange?.();
}

export function isChatTitleGenerating(chatId: string): boolean {
  return _pendingTitleChatIds.has(chatId);
}

export function subscribeChatTitleGenerating(fn: () => void) {
  _onTitlePendingChange = fn;
  return () => {
    if (_onTitlePendingChange === fn) _onTitlePendingChange = null;
  };
}

/** Metadata changes shared by the drawer and the currently open conversation. */
type ChatChangeListener = (chatId: string, patch: Partial<Chat> | null) => void;
const chatChangeListeners = createListenerSet<Parameters<ChatChangeListener>>();
let mutationSession = -1;
const chatMutationRevisions = new Map<string, number>();

export function getChatMutationRevision(chatId: string): number {
  if (mutationSession !== getSessionGeneration()) {
    mutationSession = getSessionGeneration();
    chatMutationRevisions.clear();
  }
  return chatMutationRevisions.get(chatId) ?? 0;
}

export function publishChatChange(chatId: string, patch: Partial<Chat> | null): void {
  chatMutationRevisions.set(chatId, getChatMutationRevision(chatId) + 1);
  chatChangeListeners.emit(chatId, patch);
}

export function subscribeChatChanges(listener: ChatChangeListener): () => void {
  return chatChangeListeners.subscribe(listener);
}
