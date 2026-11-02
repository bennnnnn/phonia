import { attachmentRecordExists, attachmentsApi } from "@/features/attachments/api";
import { request } from "@/lib/api/client";
import { removeCachedAttachmentFiles } from "@/features/attachments/model/downloadChatAttachment";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  removeCachedAttachmentFiles: jest.fn(async () => undefined),
}));
jest.mock("@/lib/deviceTimezone", () => ({
  getDeviceTimezone: () => "America/Los_Angeles",
}));
jest.mock("@/lib/api/client", () => ({
  request: jest.fn(),
}));

const mockRequest = request as jest.Mock;

describe("domain API contracts", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequest.mockResolvedValue({});
  });

  it("encodes gallery filters and pagination", async () => {
    await attachmentsApi.listAttachments("token", {
      category: "images",
      source: "generated",
      limit: 30,
      cursor: "after-60",
    });
    expect(mockRequest).toHaveBeenCalledWith(
      "/attachments?category=images&source=generated&limit=30&cursor=after-60",
      "token",
    );
  });

  it("encodes gallery search query", async () => {
    await attachmentsApi.listAttachments("token", { q: "see you later" });
    expect(mockRequest).toHaveBeenCalledWith("/attachments?q=see+you+later", "token");
  });

  it("deletes a Library attachment", async () => {
    await attachmentsApi.deleteAttachment("token", "att-1");
    expect(mockRequest).toHaveBeenCalledWith("/attachments/att-1", "token", {
      method: "DELETE",
    });
    expect(removeCachedAttachmentFiles).toHaveBeenCalledWith("att-1");
  });

  it("retains cached files when server deletion fails", async () => {
    mockRequest.mockRejectedValueOnce(new Error("Offline"));
    await expect(attachmentsApi.deleteAttachment("token", "att-1")).rejects.toThrow("Offline");
    expect(removeCachedAttachmentFiles).not.toHaveBeenCalled();
  });

  it("does not turn successful remote deletion into an error if cache cleanup fails", async () => {
    jest
      .mocked(removeCachedAttachmentFiles)
      .mockRejectedValueOnce(new Error("Storage unavailable"));
    await expect(attachmentsApi.deleteAttachment("token", "att-1")).resolves.toBeUndefined();
  });

  it("probes GET /url to see if a Library record still exists", async () => {
    mockRequest.mockResolvedValue({ id: "a" });
    await expect(attachmentRecordExists("token", "a")).resolves.toBe(true);
    expect(mockRequest).toHaveBeenCalledWith("/attachments/a/url", "token");

    mockRequest.mockRejectedValue(Object.assign(new Error("gone"), { status: 404 }));
    await expect(attachmentRecordExists("token", "gone")).resolves.toBe(false);

    mockRequest.mockRejectedValue(new Error("offline"));
    await expect(attachmentRecordExists("token", "a")).resolves.toBeNull();
  });
});
