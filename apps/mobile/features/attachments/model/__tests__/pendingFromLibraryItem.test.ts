import { ensureLocalAttachmentFile } from "@/features/attachments/model/downloadChatAttachment";
import { pendingFromLibraryItem } from "@/features/attachments/model/pendingFromLibraryItem";

let mockGeneration = 0;
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockGeneration,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error { constructor() { super("Session changed"); } },
}));

jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  ensureLocalAttachmentFile: jest.fn(),
}));

jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: ({ attachmentId }: { attachmentId: string }) =>
    `http://api.test/attachments/${attachmentId}/file`,
}));

beforeEach(() => {
  mockGeneration = 0;
  jest.mocked(ensureLocalAttachmentFile).mockReset().mockImplementation(async ({ fileName }) => `file:///cache/${fileName}`);
});

describe("pendingFromLibraryItem", () => {
  it("downloads images and skips re-upload via existingAttachmentId", async () => {
    const pending = await pendingFromLibraryItem(
      {
        id: "img-1",
        content_type: "image/png",
        original_filename: "cat.png",
        download_url: "/attachments/img-1/file",
      },
      "tok",
    );

    expect(ensureLocalAttachmentFile).toHaveBeenCalled();
    expect(pending).toMatchObject({
      kind: "image",
      fileName: "cat.png",
      existingAttachmentId: "img-1",
    });
  });

  it("retains a local document copy for draft recovery", async () => {
    const pending = await pendingFromLibraryItem(
      {
        id: "doc-1",
        content_type: "application/pdf",
        original_filename: "notes.pdf",
        download_url: "/attachments/doc-1/file",
      },
      "tok",
    );

    expect(ensureLocalAttachmentFile).toHaveBeenCalledWith({
      uri: "http://api.test/attachments/doc-1/file", token: "tok", fileName: "notes.pdf",
    });
    expect(pending).toMatchObject({
      kind: "file",
      fileName: "notes.pdf",
      existingAttachmentId: "doc-1",
      localUri: "file:///cache/notes.pdf",
    });
  });
});


it.each(["image/jpeg", "application/pdf"])("does not return a previous account's Library selection after downloading %s", async (contentType) => {
  jest.mocked(ensureLocalAttachmentFile).mockImplementationOnce(async () => {
    mockGeneration++;
    return "file:///old-account.jpg";
  });
  await expect(pendingFromLibraryItem({
    id: "old-image", content_type: contentType, original_filename: "image.jpg", download_url: "/attachments/old-image/file",
  }, "old-token")).rejects.toThrow("Session changed");
});


it("surfaces a failed document download instead of retaining an unusable remote URI", async () => {
  jest.mocked(ensureLocalAttachmentFile).mockRejectedValueOnce(new Error("Download offline"));
  await expect(pendingFromLibraryItem({
    id: "doc-1", content_type: "application/pdf", original_filename: "notes.pdf", download_url: "/attachments/doc-1/file",
  }, "tok")).rejects.toThrow("Download offline");
});
