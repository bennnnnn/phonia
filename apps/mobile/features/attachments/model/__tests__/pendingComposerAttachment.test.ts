import { getSessionGeneration } from "@/lib/auth";
import {
  queueComposerAttachment,
  resetComposerAttachmentQueue,
  subscribeComposerAttachmentQueue,
  takeQueuedComposerAttachment,
} from "@/features/attachments/model/pendingComposerAttachment";
jest.mock("@/lib/auth", () => ({ getSessionGeneration: jest.fn(() => 0) }));
beforeEach(() => { (getSessionGeneration as jest.Mock).mockReturnValue(0); });

describe("pendingComposerAttachment", () => {
  afterEach(() => {
    resetComposerAttachmentQueue();
  });

  it("hands the pick to a subscriber and clears after take", () => {
    const pending = {
      localUri: "file://a.jpg",
      contentType: "image/jpeg",
      fileName: "a.jpg",
      kind: "image" as const,
      existingAttachmentId: "att-1",
    };
    const listener = jest.fn();
    const stop = subscribeComposerAttachmentQueue(listener);
    queueComposerAttachment(pending);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(takeQueuedComposerAttachment()).toEqual(pending);
    expect(takeQueuedComposerAttachment()).toBeNull();
    stop();
  });
});

it("does not consume an attachment intended for a different composer", () => {
  const pending = { localUri: "file://a.pdf", contentType: "application/pdf", fileName: "a.pdf", kind: "file" as const };
  queueComposerAttachment(pending, "chat-a");
  expect(takeQueuedComposerAttachment("chat-b")).toBeNull();
  expect(takeQueuedComposerAttachment("chat-a")).toEqual(pending);
});

it("discards an unconsumed attachment when the account session changes", () => {
  queueComposerAttachment({ localUri: "file://private.pdf", contentType: "application/pdf", fileName: "private.pdf", kind: "file" });
  (getSessionGeneration as jest.Mock).mockReturnValue(1);
  expect(takeQueuedComposerAttachment()).toBeNull();
});
