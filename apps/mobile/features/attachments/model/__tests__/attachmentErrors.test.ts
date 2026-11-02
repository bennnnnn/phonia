import { ApiRequestError } from "@/lib/api/client";
import {
  AttachmentError,
  attachmentErrorMessage,
  presignFailure,
  type AttachmentFailure,
} from "@/features/attachments/model/attachmentErrors";
import en from "@/lib/i18n/en.json";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "http://test.local" }));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));

const refused = (status: number, detail: unknown) => new ApiRequestError(status, JSON.stringify({ detail }));
const translate = (key: string, options?: Record<string, unknown>) =>
  `${key}${options?.limit ? `:${String(options.limit)}` : ""}`;

describe("presignFailure", () => {
  it.each<[ApiRequestError, AttachmentFailure]>([
    [refused(400, { code: "unsupported_type", message: "Unsupported content type" }), "unsupported_type"],
    [refused(400, { code: "invalid_size", message: "Invalid file size" }), "too_large"],
    [refused(422, [{ loc: ["body", "size_bytes"], msg: "Input should be less than or equal to 10485760" }]), "too_large"],
    [refused(429, { code: "daily_limit", message: "Reworded limit." }), "daily_limit"],
    [refused(400, "Unsupported content type"), "upload_failed"],
    [refused(503, { code: "unavailable", message: "Attachment storage is not configured" }), "upload_failed"],
    [refused(422, [{ loc: ["body", "filename"], msg: "String should have at most 255 characters" }]), "upload_failed"],
    [new ApiRequestError(500, "Internal Server Error"), "upload_failed"],
  ])("names the API's refusal %#", (error, reason) => {
    expect(presignFailure(error)).toMatchObject({ name: "AttachmentError", reason });
  });

  it("passes a session change or a network failure through", () => {
    const offline = new TypeError("Network request failed");
    expect(presignFailure(offline)).toBe(offline);
  });
});

describe("attachmentErrorMessage", () => {
  it.each<[unknown, string]>([
    [new AttachmentError("too_large"), "chat.attach_too_large:10"],
    [new AttachmentError("unsupported_type"), "chat.attach_unsupported_type:10"],
    [new AttachmentError("camera_permission"), "chat.camera_permission:10"],
    [new Error("{\"detail\":\"Invalid file size\"}"), "chat.attach_failed"],
    ["not an error", "chat.attach_failed"],
    // Offline at the presign: no answer from Recall, said as everywhere else.
    [new TypeError("Network request failed"), "chat.error_unreachable"],
  ])("maps %p to a message key, never raw text", (error, message) => {
    expect(attachmentErrorMessage(error, translate)).toBe(message);
  });

  it("has an English message for every reason", () => {
    const reasons: AttachmentFailure[] = [
      "too_large", "unsupported_type", "unreadable", "changed", "upload_failed", "daily_limit", "camera_permission",
    ];
    const keys = reasons.map((reason) => attachmentErrorMessage(new AttachmentError(reason), (key) => key));
    for (const key of keys) expect(en).toHaveProperty([key]);
    expect(en["chat.attach_too_large"]).toContain("{{limit}}");
  });
});
