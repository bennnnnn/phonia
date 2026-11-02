import type React from "react";
import { act, renderHook } from "@testing-library/react-native";

import { useChatImageGeneration } from "@/features/chat/hooks/useChatImageGeneration";
import { api, type Message } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { serverUnreachableError } from "@/lib/api/deadline";
import { AttachmentError } from "@/features/attachments/model/attachmentErrors";
import { uploadChatAttachment } from "@/features/attachments/model/attachments";
import i18n, { ensureLocale } from "@/lib/i18n";
import de from "@/lib/i18n/de.json";
import fixture from "../../../../../../docs/fixtures/error_codes.json";

jest.mock("@/lib/api", () => ({ api: { generateImage: jest.fn() } }));
jest.mock("@/lib/api/client", () => ({
  ApiRequestError: jest.requireActual("@/lib/api/errorBody").ApiRequestError,
}));
jest.mock("@/features/attachments/model/attachments", () => ({ uploadChatAttachment: jest.fn() }));
jest.mock("@/lib/haptics", () => ({ notifyWarning: jest.fn() }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableError: jest.fn() }));

type Translate = (key: string) => string;

async function failedRow(
  isPaid: boolean,
  error: Error,
  t: Translate = (key) => key,
  reference?: { localUri: string; contentType: string; fileName: string; kind: "image" },
): Promise<Message | undefined> {
  (api.generateImage as jest.Mock).mockRejectedValueOnce(error);
  const updates: React.SetStateAction<Message[]>[] = [];
  const { result } = await renderHook(() => useChatImageGeneration({
    token: "tok",
    ensureChatId: async () => "chat",
    editThread: (update) => { updates.push(update); },
    streaming: false,
    isPaid,
    isOffline: false,
    onOpenUpgrade: jest.fn(),
    onScrollToLatest: jest.fn(),
    newMessageCountRef: { current: 0 },
    t,
  }));
  await act(async () => {
    await result.current.submitPrompt({ prompt: "cat", userMessage: "Draw a cat", referenceAttachment: reference });
  });
  const rows = updates.reduce<Message[]>((list, update) => (typeof update === "function" ? update(list) : update), []);
  return rows.at(-1);
}

const refusal = (status: number, code: string, message: string) =>
  new ApiRequestError(status, JSON.stringify({ detail: { code, message } }));

it.each([
  [true, "chat.image_daily_limit_paid"],
  [false, "chat.image_daily_limit_free"],
])("names the picture's own limit, not the chat allowance (isPaid %p)", async (isPaid, message) => {
  const row = await failedRow(isPaid, refusal(429, "daily_limit", "Image limit."));
  // Retry would meet the same cap until tomorrow: the card offers none.
  expect(row).toMatchObject({ image_gen_failure: "failed", image_gen_error: message, image_gen_refused: true });
});

it("offers no Retry for a picture the content rules refused", async () => {
  const row = await failedRow(true, refusal(422, "content_blocked", "Blocked."));
  expect(row).toMatchObject({ image_gen_error: "chat.image_content_blocked", image_gen_refused: true });
});

it.each([
  ["a provider failure", refusal(502, "upstream_failed", "Could not generate image")],
  ["a dropped connection", new Error("Network request failed")],
])("keeps Retry after %s", async (_label, error) => {
  const row = await failedRow(true, error);
  expect(row).toMatchObject({ image_gen_failure: "failed", image_gen_refused: undefined });
});

// The image service's 502 (modules/images/generation.py) showed its English on the card.
it("words a provider failure in the phone's language", async () => {
  const failed = fixture.image_upstream_failed;
  const row = await failedRow(false, refusal(failed.status, failed.detail.code, failed.detail.message));
  expect(row).toMatchObject({ image_gen_error: "chat.image_gen_failed", image_gen_refused: undefined });
});

// No answer from Recall, or a reference photo the phone could not upload: the card showed the
// English as it came, in every language ("Could not reach the Recall server…",
// "ATTACHMENT_TOO_LARGE").
describe("a picture that failed before the API answered, on a German phone", () => {
  let german: Translate;
  beforeAll(async () => {
    await ensureLocale("de");
    german = i18n.getFixedT("de");
  });
  afterAll(async () => { await ensureLocale("en"); });
  afterEach(() => { jest.mocked(api.generateImage).mockReset(); });

  it.each([
    ["a refresh past its deadline", serverUnreachableError()],
    ["no connection", new TypeError("Network request failed")],
  ])("says it got no answer (%s) in German, with Retry", async (_label, error) => {
    const row = await failedRow(false, error, german);
    expect(row).toMatchObject({ image_gen_error: de["chat.error_unreachable"], image_gen_refused: undefined });
  });

  // The day's spend cap (modules/images/generation.py): its English showed on the card.
  it("says the picture's spend cap in German, with Retry", async () => {
    const capped = fixture.image_spend_cap;
    const row = await failedRow(false, refusal(capped.status, capped.detail.code, capped.detail.message), german);
    expect(row).toMatchObject({ image_gen_error: de["chat.image_spend_cap"], image_gen_refused: undefined });
  });

  it("names a reference photo that was too large in German", async () => {
    jest.mocked(uploadChatAttachment).mockRejectedValueOnce(new AttachmentError("too_large"));
    const photo = { localUri: "file://ref.jpg", contentType: "image/jpeg", fileName: "ref.jpg", kind: "image" as const };
    const row = await failedRow(false, new Error("unused"), german, photo);
    expect(row).toMatchObject({ image_gen_error: de["chat.attach_too_large"].replace("{{limit}}", "10") });
  });
});
