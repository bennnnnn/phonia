/** Sign-out leaves nothing of the account for the next one (see accountState.test.ts). */
import { request } from "@/lib/api/client";
import { clearPushSyncRecord } from "@/features/notifications/model/pushNotifications";
import { quizAttempt, saveQuizAttempt } from "@/lib/lesson/quizAttempts";
import { fetchLinkPreview } from "@/lib/linkPreview";
import { latexToSvgMath, peekSvgMath, setSvgMathRendererForTest } from "@/lib/math/svgMath";
import { clearSignedOutAccount } from "@/lib/signOutCleanup";
import { getStreamingDraft, publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";
import { clearSavedProposals } from "@/features/todos/model/reminderProposal";
import { resetQuotaNudgeDismissal } from "@/features/chat/model/quotaNudgeDismissal";
import { forgetSyncRecords } from "@/lib/syncRecords";
import { clearSettledStatuses } from "@/features/attachments/model/attachmentStatusFile";

const mockFiles: Record<string, string[]> = {};
const mockDeleted: string[] = [];

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  readDirectoryAsync: jest.fn(async (directory: string) => {
    if (!(directory in mockFiles)) throw new Error("no such directory");
    return mockFiles[directory];
  }),
  deleteAsync: jest.fn(async (path: string) => {
    mockDeleted.push(path);
  }),
}));
jest.mock("@/lib/api/client", () => ({
  request: jest.fn(async () => ({ url: "https://a.example", title: "A", description: null, domain: "a.example" })),
}));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ clearPushSyncRecord: jest.fn(async () => undefined) }));
jest.mock("@/lib/auth", () => ({ getToken: jest.fn(async () => "token") }));
jest.mock("@/lib/cachedModels", () => ({ clearCachedModels: jest.fn(async () => undefined) }));
jest.mock("@/lib/syncRecords", () => ({ forgetSyncRecords: jest.fn(async () => undefined) }));
jest.mock("@/lib/google-auth", () => ({ signOutGoogle: jest.fn(async () => undefined) }));
jest.mock("@/features/chat/model/composerDraftReset", () => ({ resetComposerDraftsForAccount: jest.fn() }));
jest.mock("@/features/todos/model/reminderProposal", () => ({ clearSavedProposals: jest.fn() }));
jest.mock("@/features/chat/model/quotaNudgeDismissal", () => ({ resetQuotaNudgeDismissal: jest.fn() }));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({ clearLocalAttachmentFileCache: jest.fn() }));
jest.mock("@/features/attachments/model/attachmentStatusFile", () => ({ clearSettledStatuses: jest.fn() }));
jest.mock("@/features/todos/model/todoReminders", () => ({ cancelAllTodoReminders: jest.fn() }));
jest.mock("@/features/chat/model/messageCache", () => ({ clearAllCachedChatMessages: jest.fn() }));
jest.mock("@/features/memory/model/memoryListCache", () => ({ invalidateMemoriesCache: jest.fn() }));
jest.mock("@/features/attachments/model/galleryListCache", () => ({ invalidateGalleryCache: jest.fn() }));
jest.mock("@/features/chat/model/chatListCache", () => ({ invalidateChatListCache: jest.fn() }));
jest.mock("@/lib/cache/usageCache", () => ({ invalidateUsageCache: jest.fn() }));
jest.mock("@/features/billing/model/purchases", () => ({ signOutRevenueCat: jest.fn() }));
jest.mock("@/features/todos/model/reminderSeen", () => ({ clearSeenReminderIds: jest.fn() }));
jest.mock("@/features/todos/model/homeReminderNudges", () => ({ clearHomeNudgeState: jest.fn() }));

beforeEach(() => {
  mockDeleted.length = 0;
  for (const key of Object.keys(mockFiles)) delete mockFiles[key];
  jest.clearAllMocks();
});

it("forgets the quiz answers, link previews, maths and the reply still streaming", async () => {
  saveQuizAttempt("quiz-fence", { picked: 2, checked: true });
  await fetchLinkPreview("https://a.example");
  setSvgMathRendererForTest(() => "<mjx-container><svg width=\"1ex\" height=\"1ex\"></svg></mjx-container>");
  await latexToSvgMath("x^2", false);
  expect(peekSvgMath("x^2", false)).not.toBeUndefined();
  publishStreamingDraft({ content: "Your test results say" });

  await clearSignedOutAccount("user-1");

  expect(quizAttempt("quiz-fence")).toBeUndefined();
  expect(peekSvgMath("x^2", false)).toBeUndefined();
  expect(getStreamingDraft()).toBeNull();
  await fetchLinkPreview("https://a.example");
  expect(request).toHaveBeenCalledTimes(2);
  expect(clearSavedProposals).toHaveBeenCalled();
  // The server forgets the device's push token with the session.
  expect(clearPushSyncRecord).toHaveBeenCalled();
  expect(resetQuotaNudgeDismissal).toHaveBeenCalled();
  // The next sign-in registers for push and reads the location afresh.
  expect(forgetSyncRecords).toHaveBeenCalled();
  // The files' names and statuses this account's chats showed.
  expect(clearSettledStatuses).toHaveBeenCalled();
});

it("deletes the account's export, previews, read-aloud audio and PDFs, and nothing else", async () => {
  mockFiles["file:///cache/"] = [
    "recall-export-1.json",
    "recall-preview-2.html",
    "recall-tts-3.mp3",
    "cached-user.json",
    "recall-scanner-switch-left.wav",
    "Print",
  ];
  mockFiles["file:///cache/Print/"] = ["0A1B.pdf", "notes.txt"];
  // Voice recordings expo-audio wrote (iOS, Android): never kept past sign-out (LEAK-04).
  mockFiles["file:///cache/ExpoAudio/"] = ["recording-1.m4a", "other.caf"];
  mockFiles["file:///cache/Audio/"] = ["recording-2.m4a"];

  await clearSignedOutAccount("user-1");

  expect(mockDeleted.sort()).toEqual([
    "file:///cache/Audio/recording-2.m4a",
    "file:///cache/ExpoAudio/recording-1.m4a",
    "file:///cache/Print/0A1B.pdf",
    "file:///cache/recall-export-1.json",
    "file:///cache/recall-preview-2.html",
    "file:///cache/recall-tts-3.mp3",
  ]);
});

it("still clears memory when the cache directory cannot be read", async () => {
  saveQuizAttempt("quiz-fence", { picked: 1, checked: false });
  await clearSignedOutAccount(undefined);
  expect(quizAttempt("quiz-fence")).toBeUndefined();
  expect(mockDeleted).toEqual([]);
});
