/**
 * The chat share sheet's PDF button: a build that cannot share files (Android without
 * expo-sharing, lib/shareFile.ts) says to update the app, not the generic "PDF failed".
 */
import { render } from "@testing-library/react-native";

import { ChatShareSheet } from "@/features/chat/components/ChatShareSheet";
import { exportConversationAsPdf } from "@/features/chat/model/exportMessagePdf";
import { NothingToExportError } from "@/features/chat/model/nothingToExport";
import { SharingUnavailableError } from "@/lib/shareUnavailable";

type SheetProps = { onExportPdf: () => Promise<void>; failureText: (error: unknown) => string | null };
let sheet: SheetProps;
jest.mock("@/ui/share/ShareSheet", () => ({
  ShareSheet: (props: SheetProps) => {
    sheet = props;
    return null;
  },
}));
jest.mock("@/features/chat/model/exportMessagePdf", () => ({ exportConversationAsPdf: jest.fn() }));

async function failedPdfWords(failure: Error): Promise<string | null> {
  jest.mocked(exportConversationAsPdf).mockRejectedValueOnce(failure);
  await render(<ChatShareSheet visible onClose={jest.fn()} title="Plans" loadMessages={async () => []} />);
  const error = await sheet.onExportPdf().then(() => null, (thrown: unknown) => thrown);
  expect(error).toBe(failure);
  return sheet.failureText(error);
}

it.each([
  ["a build that cannot share files", new SharingUnavailableError(), "common.share_needs_update"],
  ["an empty chat", new NothingToExportError(), "chat.export_pdf_empty"],
  ["any other failure (the sheet's own line)", new Error("print failed"), null],
])("words a PDF that failed with %s", async (_label, failure, words) => {
  expect(await failedPdfWords(failure)).toBe(words);
});
