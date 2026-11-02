import { act, renderHook } from "@testing-library/react-native";

import { useSendAttachment, uploadSendAttachment } from "@/features/chat/hooks/useSendAttachment";
import { uploadChatAttachment, type PendingAttachment } from "@/features/attachments/model/attachments";
import { reportFailure } from "@/lib/sentry";

const mockDiscard = jest.fn();
jest.mock("@/features/attachments/model/attachments", () => ({
  discardDraftAttachment: (...args: unknown[]) => mockDiscard(...args),
  uploadChatAttachment: jest.fn(),
}));
jest.mock("@/lib/sentry", () => ({ reportFailure: jest.fn() }));

const file = (name: string): PendingAttachment => ({
  localUri: `file:///cache/DocumentPicker/${name}`, contentType: "application/pdf", fileName: name, kind: "file",
});

beforeEach(() => jest.clearAllMocks());

describe("useSendAttachment thread drafts", () => {
  it("brings a failed send's attachment back when its thread opens", async () => {
    const { result } = await renderHook(() => useSendAttachment("token"));
    const failed = file("failed.pdf");
    await act(async () => { result.current.stashAttachmentForThread("chat-1", "chat-2", failed); });
    await act(async () => { result.current.switchAttachmentThread("chat-2", "chat-1"); });
    expect(result.current.pendingAttachment).toBe(failed);
    expect(mockDiscard).not.toHaveBeenCalled();
  });

  it.each([
    ["the slot already holds a newer attachment", "chat-2"],
    ["the failed send's thread is the open one", "chat-1"],
  ])("discards a failed send's attachment when %s", async (_name, openKey) => {
    const { result } = await renderHook(() => useSendAttachment("token"));
    const newer = file("newer.pdf");
    const failed = { ...file("failed.pdf"), existingAttachmentId: "up-1", uploadedForDraft: true };
    if (openKey === "chat-2") {
      await act(async () => { result.current.setPendingAttachment(newer); });
      await act(async () => { result.current.switchAttachmentThread("chat-1", "chat-2"); });
    }
    await act(async () => { result.current.stashAttachmentForThread("chat-1", openKey, failed); });
    expect(mockDiscard).toHaveBeenCalledWith("token", failed);
  });

  it("drops every draft's copy on an account change, without the new token", async () => {
    const { result } = await renderHook(() => useSendAttachment("token"));
    const waiting = file("waiting.pdf");
    const open = file("open.pdf");
    await act(async () => { result.current.stashAttachmentForThread("chat-1", "chat-2", waiting); });
    await act(async () => { result.current.setPendingAttachment(open); });
    await act(async () => { result.current.resetAttachmentDrafts(); });
    expect(result.current.pendingAttachment).toBeNull();
    expect(mockDiscard.mock.calls).toEqual([[null, waiting], [null, open]]);
  });

  it("drops held copies when the composer unmounts", async () => {
    const { result, unmount } = await renderHook(() => useSendAttachment("token"));
    const open = file("open.pdf");
    await act(async () => { result.current.setPendingAttachment(open); });
    await unmount();
    expect(mockDiscard).toHaveBeenCalledWith(null, open);
  });
});

describe("uploadSendAttachment", () => {
  it.each([
    ["a fresh pick", file("new.pdf"), true],
    ["a Library pick", { ...file("lib.pdf"), existingAttachmentId: "lib-1" }, false],
    ["a re-upload of a draft's own rejected file", { ...file("again.pdf"), uploadedForDraft: true }, true],
  ])("marks %s as this draft's upload: %p", async (_name, attachment, owned) => {
    jest.mocked(uploadChatAttachment).mockResolvedValueOnce("id-1");
    const { attachment: uploaded } = await uploadSendAttachment("token", attachment);
    expect(uploaded).toMatchObject({ existingAttachmentId: "id-1", uploadedForDraft: owned });
    expect(reportFailure).not.toHaveBeenCalled();
  });

  it("reports a failed upload and throws it on for the caller's toast", async () => {
    const failure = new Error("presign refused");
    jest.mocked(uploadChatAttachment).mockRejectedValueOnce(failure);
    await expect(uploadSendAttachment("token", file("big.pdf"))).rejects.toBe(failure);
    expect(reportFailure).toHaveBeenCalledWith("attachment_upload", failure);
  });
});
