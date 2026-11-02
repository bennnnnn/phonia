import { resetComposerDraftsForAccount } from "@/features/chat/model/composerDraftReset";
import { deleteAccountFiles } from "@/lib/accountFiles";
import { clearCachedModels } from "@/lib/cachedModels";
import { signOutGoogle } from "@/lib/google-auth";
import { clearQuizAttempts } from "@/lib/lesson/quizAttempts";
import { clearCalculatorPositions } from "@/lib/money/calculatorPositions";
import { clearLinkPreviewCache } from "@/lib/linkPreview";
import { clearSvgMathCache } from "@/lib/math/svgMath";
import { publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";
import { forgetSyncRecords } from "@/lib/syncRecords";

/** Device/account side effects finish before another account signs in, so it
 * starts with nothing of this one. Every store that can hold an account's data
 * is cleared here or scoped to the session (`lib/__tests__/accountState.test.ts`).
 * Backend session revocation is separate, so an offline server never holds logout UI. */
export async function clearSignedOutAccount(userId: string | undefined): Promise<void> {
  resetComposerDraftsForAccount();
  clearQuizAttempts();
  clearCalculatorPositions();
  clearLinkPreviewCache();
  clearSvgMathCache();
  publishStreamingDraft(null);
  await Promise.allSettled([
    deleteAccountFiles(),
    forgetSyncRecords(),
    import("@/features/todos/model/reminderProposal").then(({ clearSavedProposals }) => clearSavedProposals()),
    import("@/features/chat/model/quotaNudgeDismissal").then(({ resetQuotaNudgeDismissal }) => resetQuotaNudgeDismissal()),
    import("@/features/attachments/model/downloadChatAttachment").then(({ clearLocalAttachmentFileCache }) => clearLocalAttachmentFileCache()),
    import("@/features/attachments/model/attachmentStatusFile").then(({ clearSettledStatuses }) => clearSettledStatuses()),
    import("@/features/todos/model/todoReminders").then(({ cancelAllTodoReminders }) => cancelAllTodoReminders()),
    import("@/features/chat/model/messageCache").then(({ clearAllCachedChatMessages }) => clearAllCachedChatMessages()),
    import("@/features/memory/model/memoryListCache").then(({ invalidateMemoriesCache }) => invalidateMemoriesCache()),
    import("@/features/attachments/model/galleryListCache").then(({ invalidateGalleryCache }) => invalidateGalleryCache()),
    import("@/features/chat/model/chatListCache").then(({ invalidateChatListCache }) => invalidateChatListCache()),
    import("@/lib/cache/usageCache").then(({ invalidateUsageCache }) => invalidateUsageCache()),
    import("@/features/notifications/model/pushNotifications").then(({ clearPushSyncRecord }) => clearPushSyncRecord()),
    clearCachedModels(),
    import("@/features/billing/model/purchases").then(({ signOutRevenueCat }) => signOutRevenueCat()),
    signOutGoogle(),
    ...(userId ? [
      import("@/features/todos/model/reminderSeen").then(({ clearSeenReminderIds }) => clearSeenReminderIds(userId)),
      import("@/features/todos/model/homeReminderNudges").then(({ clearHomeNudgeState }) => clearHomeNudgeState(userId)),
    ] : []),
  ]);
}
