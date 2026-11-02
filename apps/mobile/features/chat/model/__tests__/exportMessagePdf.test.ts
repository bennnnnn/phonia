import { exportConversationAsPdf } from "@/features/chat/model/exportMessagePdf";
import { NothingToExportError } from "@/features/chat/model/nothingToExport";
import type { Message } from "@/lib/api";
import { printHtmlToSharedPdf } from "@/features/chat/model/exportPdf";
import { markdownToStructuredPrintHtml } from "@/features/chat/model/printDocument";

jest.mock("@/lib/i18n", () => ({ __esModule: true, default: { t: (key: string) => key } }));
jest.mock("@/features/chat/model/exportPdf", () => ({ printHtmlToSharedPdf: jest.fn(async () => undefined) }));
jest.mock("@/features/chat/model/printDocument", () => ({
  markdownToStructuredPrintHtml: jest.fn(async (_title: string, md: string) => `<p>${md}</p>`),
}));

it("says there is nothing to export instead of printing a blank page", async () => {
  const onlyCard = [
    { id: "a1", role: "assistant", content: '```reminder_proposal\n{"proposal_id":"p"}\n```' },
  ] as Message[];
  await expect(exportConversationAsPdf("Trip", onlyCard)).rejects.toBeInstanceOf(NothingToExportError);
  expect(printHtmlToSharedPdf).not.toHaveBeenCalled();
});

it("prints a card's lines a hard break apart, so the PDF keeps each on its own line", async () => {
  const quiz = '```quiz\n{"question":"Pick","options":["a","b"],"answer":1}\n```';
  await exportConversationAsPdf("Quiz", [{ id: "a1", role: "assistant", content: quiz }] as Message[]);
  expect(markdownToStructuredPrintHtml).toHaveBeenCalledWith(
    "Quiz",
    expect.stringContaining("Pick  \nA) a  \nB) b"),
  );
});

it("prints a chat with text under its title", async () => {
  await exportConversationAsPdf("Trip", [{ id: "u1", role: "user", content: "hello" }] as Message[]);
  expect(printHtmlToSharedPdf).toHaveBeenCalledWith(expect.stringContaining("hello"), "Trip");
});
