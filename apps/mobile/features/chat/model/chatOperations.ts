/**
 * Rename, pin, archive and delete one chat: the one implementation the drawer's row menu
 * and the chat header's menu share, so a failure reads and recovers the same in both.
 * Each change shows at once, is saved, then takes the server's answer; a failed save
 * puts the chat back as it was and says what failed.
 */

import { abandonActiveChatIfDeleted } from "@/features/chat/drawer/drawer";
import { getCachedChat, peekCreatedChat } from "@/features/chat/model/chatListCache";
import { clearCachedChatMessages } from "@/features/chat/model/messageCache";
import { beginChatMutation } from "@/features/chat/model/mutationLock";
import { sanitizeManualChatTitle } from "@/features/chat/model/title";
import { api, type Chat } from "@/lib/api";
import { emitAppEvent } from "@/lib/appEvents";
import { notifyDestructive } from "@/lib/haptics";
import type { IconName } from "@/ui/icons/names";
import { confirmDialog } from "@/ui/overlay/dialogs";

/** What an operation needs to know about the chat as the person sees it now. */
type ChatRef = Pick<Chat, "id" | "title" | "pinned" | "archived">;

export type ChatOperationContext = {
  token: string;
  /** The sign-in the change started under (`getSessionGeneration`). */
  session: number;
  /** The drawer list's own updates (the header uses the drawer's registered ones). */
  list: {
    patch: (chatId: string, patch: Partial<Chat>) => void;
    insert: (chat: Chat) => void;
    remove: (chatId: string) => void;
  };
  /** The same account is signed in: the list may still change. */
  signedIn: () => boolean;
  /** The menu's screen is still up: it may still show a message or mirror the change. */
  shown: () => boolean;
  /** The asking screen's own copy of the chat (the header's title, pin and archive). */
  mirror?: (patch: Partial<Chat>) => void;
  banner: (message: string, icon: IconName) => void;
  failure: (message: string) => void;
  t: (key: string) => string;
};

function apply(ctx: ChatOperationContext, chatId: string, patch: Partial<Chat>): void {
  ctx.list.patch(chatId, patch);
  if (ctx.shown()) ctx.mirror?.(patch);
}

/**
 * Rename to `rawTitle`. A blank title saves nothing and says so; false keeps the
 * rename sheet open for another try.
 */
export function renameChat(ctx: ChatOperationContext, chat: ChatRef, rawTitle: string): boolean {
  const title = sanitizeManualChatTitle(rawTitle);
  if (!title) {
    ctx.failure(ctx.t("chat.rename_blank"));
    return false;
  }
  void saveTitle(ctx, chat, title);
  return true;
}

async function saveTitle(ctx: ChatOperationContext, chat: ChatRef, title: string): Promise<void> {
  const release = beginChatMutation(ctx.session, [chat.id]);
  if (!release) return;
  apply(ctx, chat.id, { title });
  try {
    const saved = await api.renameChat(ctx.token, chat.id, title);
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { title: saved.title });
    if (ctx.shown()) ctx.banner(ctx.t("chat.renamed_toast"), "pencil");
  } catch {
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { title: chat.title });
    if (ctx.shown()) ctx.failure(ctx.t("chat.rename_failed"));
  } finally {
    release();
  }
}

/** Pin or unpin. An archived chat has no pin. */
export async function setChatPinned(
  ctx: ChatOperationContext,
  chat: ChatRef,
  pinned: boolean,
): Promise<void> {
  if (chat.archived) return;
  const release = beginChatMutation(ctx.session, [chat.id]);
  if (!release) return;
  apply(ctx, chat.id, { pinned });
  try {
    const saved = await api.setPin(ctx.token, chat.id, pinned);
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { pinned: saved.pinned, archived: Boolean(saved.archived) });
    if (ctx.shown()) {
      ctx.banner(
        ctx.t(saved.pinned ? "chat.pinned_toast" : "chat.unpinned_toast"),
        saved.pinned ? "pin" : "pin-off",
      );
    }
  } catch {
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { pinned: chat.pinned });
    if (ctx.shown()) ctx.failure(ctx.t("chat.pin_failed"));
  } finally {
    release();
  }
}

/** Archive (which unpins) or bring back. */
export async function setChatArchived(
  ctx: ChatOperationContext,
  chat: ChatRef,
  archived: boolean,
): Promise<void> {
  const release = beginChatMutation(ctx.session, [chat.id]);
  if (!release) return;
  apply(ctx, chat.id, archived ? { archived, pinned: false } : { archived });
  try {
    const saved = await api.setArchive(ctx.token, chat.id, archived);
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { archived: Boolean(saved.archived), pinned: saved.pinned });
    if (ctx.shown()) {
      ctx.banner(
        ctx.t(saved.archived ? "chat.archived_toast" : "chat.unarchived_toast"),
        saved.archived ? "archive" : "unarchive",
      );
    }
  } catch {
    if (!ctx.signedIn()) return;
    apply(ctx, chat.id, { archived: Boolean(chat.archived), pinned: chat.pinned });
    if (ctx.shown()) ctx.failure(ctx.t("chat.archive_failed"));
  } finally {
    release();
  }
}

/** Ask, then delete. `known` is the chat as the menu had it, for a restore. */
export function confirmAndDeleteChat(ctx: ChatOperationContext, chatId: string, known?: Chat): void {
  void confirmDialog({
    title: ctx.t("chat.delete_confirm_title"),
    message: ctx.t("chat.delete_confirm_body"),
    cancelLabel: ctx.t("common.cancel"),
    confirmLabel: ctx.t("common.delete"),
    destructive: true,
  }).then(async (ok) => {
    if (!ok || !ctx.shown()) return;
    await deleteChat(ctx, chatId, known);
  });
}

async function deleteChat(ctx: ChatOperationContext, chatId: string, known?: Chat): Promise<void> {
  const release = beginChatMutation(ctx.session, [chatId]);
  if (!release) return;
  const snapshot = getCachedChat(chatId) ?? peekCreatedChat(chatId) ?? known ?? null;
  ctx.list.remove(chatId);
  try {
    await api.deleteChat(ctx.token, chatId);
    if (!ctx.signedIn()) return;
    notifyDestructive();
    ctx.list.remove(chatId);
    void clearCachedChatMessages(chatId);
    emitAppEvent("chatsDeleted", { chatIds: [chatId] });
    if (ctx.shown()) ctx.banner(ctx.t("chat.deleted_toast"), "trash");
    abandonActiveChatIfDeleted([chatId]);
  } catch {
    if (!ctx.signedIn()) return;
    // The chat comes back with its real dates and metadata; one missing from the
    // list is read from the server.
    const restored = snapshot ?? (await api.getChat(ctx.token, chatId).catch(() => null));
    if (!ctx.signedIn()) return;
    if (restored) ctx.list.insert(restored);
    if (ctx.shown()) ctx.failure(ctx.t("chat.delete_failed"));
  } finally {
    release();
  }
}
