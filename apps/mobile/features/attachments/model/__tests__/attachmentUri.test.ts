import {
  MAX_ATTACHMENT_THUMB_WIDTH,
  attachmentRequestHeaders,
  attachmentThumbWidth,
  recallAttachmentPath,
  resolveAttachmentUri,
} from "@/features/attachments/model/attachmentUri";
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.test/v1/" }));

it("builds one canonical API path with a configured base path and trailing slash", () => {
  expect(resolveAttachmentUri({ attachmentId: "abc", width: 300 }))
    .toBe("https://api.test/v1/attachments/abc/file?w=300");
});

it("caps a thumbnail width at what the API accepts (a tablet tile asks for more)", () => {
  expect(MAX_ATTACHMENT_THUMB_WIDTH).toBe(512);
  expect(attachmentThumbWidth(900)).toBe(512);
  expect(attachmentThumbWidth(240.4)).toBe(240);
  expect(attachmentThumbWidth(0)).toBe(1);
  expect(resolveAttachmentUri({ attachmentId: "abc", width: 1100 }))
    .toBe("https://api.test/v1/attachments/abc/file?w=512");
});

it("does not change signed external URLs when a thumbnail width is requested", () => {
  const path = "https://storage.test/image.jpg?signature=original";
  expect(resolveAttachmentUri({ path, width: 300 })).toBe(path);
});

it("replaces an existing API width parameter and preserves URL fragments", () => {
  expect(resolveAttachmentUri({ path: "https://api.test/v1/attachments/a/file?w=100#preview", width: 300 }))
    .toBe("https://api.test/v1/attachments/a/file?w=300#preview");
});

it.each([
  "https://api.test.external.test/v1/attachments/a/file",
  "https://api.test/v1-other/attachments/a/file",
  "https://api.test/attachments/a/file",
  "https://external.test/v1/attachments/a/file",
  "file:///image.jpg",
])("never authorizes non-API image sources: %s", (uri) => {
  expect(recallAttachmentPath(uri)).toBeNull();
  expect(attachmentRequestHeaders(uri, "token")).toEqual({});
});

it("authorizes images only within the configured API attachment route", () => {
  const uri = "https://api.test/v1/attachments/a/file?w=300";
  expect(recallAttachmentPath(uri)).toBe("/attachments/a/file?w=300");
  expect(attachmentRequestHeaders(uri, "token")).toEqual({ Authorization: "Bearer token" });
});
