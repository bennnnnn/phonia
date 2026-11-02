import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { discardLocalCopy } from "@/features/attachments/model/localAttachmentFile";
import {
  resetComposerAttachmentQueue,
  subscribeComposerAttachmentQueue,
  takeQueuedComposerAttachment,
} from "@/features/attachments/model/pendingComposerAttachment";
import {
  beginOpenedPageRead,
  OPENED_PAGE_WAIT_MS,
  whenOpenedPageSettled,
  withdrawFromOpenedPage,
} from "@/features/chat/model/openedPage";
import type { PendingSend } from "@/features/chat/model/sendLogic";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/features/attachments/model/localAttachmentFile", () => ({ discardLocalCopy: jest.fn() }));

const photo: PendingAttachment = {
  localUri: "file:///cache/picked.jpg", contentType: "image/jpeg", fileName: "picked.jpg", kind: "image",
  existingAttachmentId: "att-1", uploadedForDraft: true,
};
const turn = (overrides: Partial<PendingSend> = {}): PendingSend => ({
  content: "Next question",
  options: { composerDraft: { text: "Next question", attachment: photo } },
  messageId: "local-1",
  retryingRejected: false,
  dispatched: false,
  ...overrides,
});

/** Whether the promise settled once pending callbacks ran, and with what. */
async function settled<T>(promise: Promise<T>): Promise<{ done: boolean; value?: T }> {
  let state: { done: boolean; value?: T } = { done: false };
  void promise.then((value) => { state = { done: true, value }; });
  for (let i = 0; i < 5; i++) await Promise.resolve();
  return state;
}

describe("a turn sent while the opened chat's page is read", () => {
  const home = { stashFailedDraftForThread: jest.fn() };
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    resetComposerAttachmentQueue();
  });
  afterEach(() => jest.useRealTimers());

  it("goes at once when no page is being read for its chat", async () => {
    await expect(whenOpenedPageSettled("chat-1", turn())).resolves.toBe(true);
    await expect(whenOpenedPageSettled(null)).resolves.toBe(true);
    const other = beginOpenedPageRead("chat-2");
    await expect(whenOpenedPageSettled("chat-1", turn())).resolves.toBe(true);
    other.release();
  });

  it("waits until the page lands, then goes", async () => {
    const read = beginOpenedPageRead("chat-1");
    const waiting = whenOpenedPageSettled("chat-1", turn());
    expect(await settled(waiting)).toEqual({ done: false });
    expect(read.release()).toBe(true);
    expect(await settled(waiting)).toEqual({ done: true, value: true });
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
    await expect(whenOpenedPageSettled("chat-1", turn())).resolves.toBe(true);
  });

  it("goes after the cap, and the page that lands later is not merged", async () => {
    const read = beginOpenedPageRead("chat-1");
    const waiting = whenOpenedPageSettled("chat-1", turn());
    jest.advanceTimersByTime(OPENED_PAGE_WAIT_MS - 1);
    expect(await settled(waiting)).toEqual({ done: false });
    jest.advanceTimersByTime(1);
    expect(await settled(waiting)).toEqual({ done: true, value: true });
    expect(read.release()).toBe(false);
    // It went out, so nothing comes back if the chat then turns out to be gone.
    read.chatGone(home);
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
  });

  it("stays unsent when the view moves on, and comes back to its chat's composer, file and all", async () => {
    const read = beginOpenedPageRead("chat-1");
    const waiting = whenOpenedPageSettled("chat-1", turn());
    read.cancel(home);
    expect(await settled(waiting)).toEqual({ done: true, value: false });
    expect(home.stashFailedDraftForThread).toHaveBeenCalledWith("chat-1", "Next question");
    expect(takeQueuedComposerAttachment("new")).toBeNull();
    expect(takeQueuedComposerAttachment("chat-1")).toBe(photo);
    expect(discardLocalCopy).not.toHaveBeenCalled();
  });

  it("keeps the file from a composer still listening for the chat the view just left", async () => {
    // The route loader cleans up before the composer re-subscribes for the thread now shown.
    const leftComposer = jest.fn(() => takeQueuedComposerAttachment("chat-1"));
    const stopListening = subscribeComposerAttachmentQueue(leftComposer);
    const read = beginOpenedPageRead("chat-1");
    void whenOpenedPageSettled("chat-1", turn());
    read.cancel(home);
    stopListening();
    const shownComposer = jest.fn(() => takeQueuedComposerAttachment("chat-2"));
    const stopShown = subscribeComposerAttachmentQueue(shownComposer);
    for (let i = 0; i < 5; i++) await Promise.resolve();
    stopShown();
    expect(leftComposer).not.toHaveBeenCalled();
    expect(shownComposer).toHaveBeenCalled();
    expect(takeQueuedComposerAttachment("chat-1")).toBe(photo);
  });

  it("comes back to New Chat's composer when the chat is gone", async () => {
    const read = beginOpenedPageRead("chat-1");
    const held = turn();
    const waiting = whenOpenedPageSettled("chat-1", held);
    read.chatGone(home);
    expect(await settled(waiting)).toEqual({ done: true, value: false });
    // Marked, so a Stop that follows (New Chat stops the turn) does not hand it back a second time.
    expect(held.takenBack).toBe("page");
    expect(home.stashFailedDraftForThread).toHaveBeenCalledWith("new", "Next question");
    expect(takeQueuedComposerAttachment("new")).toBe(photo);
  });

  it("brings back the sent text when the turn had no composer draft", async () => {
    const read = beginOpenedPageRead("chat-1");
    void whenOpenedPageSettled("chat-1", turn({ content: "A follow-up question", options: {} }));
    read.chatGone(home);
    expect(home.stashFailedDraftForThread).toHaveBeenCalledWith("new", "A follow-up question");
  });

  it("leaves a retried send to its Retry when the view moves on, but not when the chat is gone", async () => {
    const left = beginOpenedPageRead("chat-1");
    void whenOpenedPageSettled("chat-1", turn({ retryingRejected: true }));
    left.cancel(home);
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
    const gone = beginOpenedPageRead("chat-1");
    void whenOpenedPageSettled("chat-1", turn({ retryingRejected: true }));
    gone.chatGone(home);
    expect(home.stashFailedDraftForThread).toHaveBeenCalledWith("new", "Next question");
  });

  it("gives nothing back after sign-out, and cleans up the file's local copy", async () => {
    const read = beginOpenedPageRead("chat-1");
    const waiting = whenOpenedPageSettled("chat-1", turn());
    read.cancel(null);
    expect(await settled(waiting)).toEqual({ done: true, value: false });
    // The file layer loads on demand.
    for (let i = 0; i < 20 && !(discardLocalCopy as jest.Mock).mock.calls.length; i++) await Promise.resolve();
    expect(discardLocalCopy).toHaveBeenCalledWith(photo.localUri);
    expect(takeQueuedComposerAttachment("chat-1")).toBeNull();
  });

  it("holds a regeneration too, with nothing to give back", async () => {
    const read = beginOpenedPageRead("chat-1");
    const waiting = whenOpenedPageSettled("chat-1", null);
    expect(await settled(waiting)).toEqual({ done: false });
    read.cancel(home);
    expect(await settled(waiting)).toEqual({ done: true, value: false });
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
  });

  it("is not ended for a newer read of the same chat by an older one", async () => {
    const older = beginOpenedPageRead("chat-1");
    const newer = beginOpenedPageRead("chat-1");
    older.release();
    const waiting = whenOpenedPageSettled("chat-1", turn());
    expect(await settled(waiting)).toEqual({ done: false });
    newer.release();
    expect(await settled(waiting)).toEqual({ done: true, value: true });
  });

  it("lets Stop withdraw a waiting turn: it says no at once, never counts as going first, and is not handed back", async () => {
    const read = beginOpenedPageRead("chat-1");
    const stopped = turn();
    const waiting = whenOpenedPageSettled("chat-1", stopped);
    withdrawFromOpenedPage("chat-1", stopped);
    expect(await settled(waiting)).toEqual({ done: true, value: false });
    jest.advanceTimersByTime(OPENED_PAGE_WAIT_MS);
    read.cancel(home);
    expect(home.stashFailedDraftForThread).not.toHaveBeenCalled();
    expect(read.release()).toBe(true);
    // Whoever sent it hands it back, so the read leaves it unmarked.
    expect(stopped.takenBack).toBeUndefined();
  });

  it("withdraws a regeneration's wait the same way, and only the turn Stop names", async () => {
    const read = beginOpenedPageRead("chat-1");
    const regenerating = whenOpenedPageSettled("chat-1", null);
    withdrawFromOpenedPage("chat-1", turn());
    expect(await settled(regenerating)).toEqual({ done: false });
    withdrawFromOpenedPage("chat-2", null);
    expect(await settled(regenerating)).toEqual({ done: false });
    withdrawFromOpenedPage("chat-1", null);
    expect(await settled(regenerating)).toEqual({ done: true, value: false });
    jest.advanceTimersByTime(OPENED_PAGE_WAIT_MS);
    expect(read.release()).toBe(true);
  });
});
