/**
 * A Library action that failed on this phone or got no answer, in the phone's language. Its
 * English showed as it came in a German Library: "Could not reach the Recall server…",
 * "Network request failed", "Could not attach", "Could not open this attachment.".
 */
import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useGalleryLibrary } from "@/features/attachments/hooks/useGalleryLibrary";
import { pendingFromLibraryItem } from "@/features/attachments/model/pendingFromLibraryItem";
import { shareChatAttachment } from "@/features/attachments/model/downloadChatAttachment";
import { api, type AttachmentListItem } from "@/lib/api";
import { serverUnreachableError } from "@/lib/api/deadline";
import { SharingUnavailableError } from "@/lib/shareUnavailable";
import { ensureLocale } from "@/lib/i18n";
import de from "@/lib/i18n/de.json";

jest.unmock("react-i18next");
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "token" }));
const mockFeedback = { error: jest.fn(), success: jest.fn(), info: jest.fn(), warning: jest.fn(), show: jest.fn(), dismiss: jest.fn() };
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => true), alertDialog: jest.fn() }));
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useRouter: () => ({ canGoBack: () => true, back: jest.fn(), replace: jest.fn() }),
    useLocalSearchParams: () => ({}),
    useFocusEffect: (callback: () => void) => useEffect(callback, [callback]),
  };
});
jest.mock("@/lib/api", () => ({ api: { deleteAttachment: jest.fn() } }));
jest.mock("@/features/attachments/model/pendingFromLibraryItem", () => ({ pendingFromLibraryItem: jest.fn() }));
jest.mock("@/features/attachments/model/galleryLayout", () => ({ getGalleryLayout: async () => "grid", peekGalleryLayout: () => "grid", setGalleryLayout: jest.fn() }));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({ shareChatAttachment: jest.fn() }));
jest.mock("@/features/attachments/model/attachmentUri", () => ({ resolveAttachmentUri: () => "https://api.test/attachments/one/file" }));
jest.mock("@/lib/haptics", () => ({ selection: jest.fn(), tap: jest.fn(), notifyDestructive: jest.fn() }));

const item = { id: "one", content_type: "image/png", download_url: "/attachments/one/file" } as AttachmentListItem;
let library: ReturnType<typeof useGalleryLibrary>;
function Probe() {
  const result = useGalleryLibrary([item], jest.fn());
  React.useLayoutEffect(() => { library = result; }, [result]);
  return <Text>Library</Text>;
}

beforeAll(async () => { await ensureLocale("de"); });
afterAll(async () => { await ensureLocale("en"); });
beforeEach(() => { jest.clearAllMocks(); });

const NO_ANSWER: [string, Error][] = [
  ["a refresh past its deadline", serverUnreachableError()],
  ["no connection", new TypeError("Network request failed")],
];

it.each(NO_ANSWER)("says a delete got no answer (%s) in German", async (_label, failure) => {
  jest.mocked(api.deleteAttachment).mockRejectedValueOnce(failure);
  await render(<Probe />);
  await act(async () => { library.confirmDelete(item); });
  await act(async () => { await Promise.resolve(); });
  expect(mockFeedback.error).toHaveBeenCalledWith(de["chat.error_unreachable"]);
});

it.each(NO_ANSWER)("says a share got no answer (%s) in German", async (_label, failure) => {
  jest.mocked(shareChatAttachment).mockRejectedValueOnce(failure);
  await render(<Probe />);
  await act(async () => { await library.shareFile(item); });
  expect(mockFeedback.error).toHaveBeenCalledWith(de["chat.error_unreachable"]);
});

it.each([
  ["an attach", "Could not attach", "chat.attach_failed"],
  ["a share", "Could not open this attachment.", "common.share_failed"],
] as const)("words %s that failed on the phone in German", async (action, english, key) => {
  if (action === "an attach") jest.mocked(pendingFromLibraryItem).mockRejectedValueOnce(new Error(english));
  else jest.mocked(shareChatAttachment).mockRejectedValueOnce(new Error(english));
  await render(<Probe />);
  await act(async () => {
    if (action === "an attach") await library.attachToComposer(item);
    else await library.shareFile(item);
  });
  expect(mockFeedback.error).toHaveBeenCalledWith(de[key]);
  expect(mockFeedback.error).not.toHaveBeenCalledWith(english);
});

// Android without expo-sharing (lib/shareFile.ts): since #2081 it read as the generic "Share failed".
it("says to update the app when this build cannot share files, in German", async () => {
  jest.mocked(shareChatAttachment).mockRejectedValueOnce(new SharingUnavailableError());
  await render(<Probe />);
  await act(async () => { await library.shareFile(item); });
  expect(mockFeedback.error).toHaveBeenCalledWith(de["common.share_needs_update"]);
});
