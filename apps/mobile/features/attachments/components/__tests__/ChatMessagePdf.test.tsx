import { act, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { ChatMessagePdf } from "@/features/attachments/components/ChatMessagePdf";
import { downloadChatAttachment } from "@/features/attachments/model/downloadChatAttachment";
import { serverUnreachableError } from "@/lib/api/deadline";
import { SharingUnavailableError } from "@/lib/shareUnavailable";
import { lightTheme as mockLightTheme } from "@/lib/theme";
import { alertDialog } from "@/ui/overlay/dialogs";

jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "tok" }));
jest.mock("@/features/attachments/hooks/useAttachmentIndexed", () => ({
  useAttachmentIndexed: () => ({ indexed: true, failed: false }),
}));
const mockPdfGuard = () => false;
jest.mock("@/features/attachments/hooks/usePdfPreview", () => ({
  usePdfPreview: () => ({
    status: "ready",
    webViewKey: "doc",
    webViewProps: { originWhitelist: ["*"], onShouldStartLoadWithRequest: mockPdfGuard },
  }),
}));
jest.mock("@/hooks/useDeferredWebViewMount", () => ({
  useDeferredWebViewMount: () => ({ canMount: true, onLoaded: jest.fn() }),
}));
jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: ({ attachmentId }: { attachmentId?: string }) => `https://api.test/attachments/${attachmentId}/file`,
}));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  downloadChatAttachment: jest.fn(),
}));
let mockShare: (() => Promise<void>) | null = null;
jest.mock("@/features/attachments/components/AttachmentPdfViewer", () => ({
  AttachmentPdfViewer: ({ onShare }: { onShare: () => Promise<void> }) => {
    mockShare = onShare;
    return null;
  },
}));
jest.mock("@/ui/overlay/dialogs", () => ({ alertDialog: jest.fn() }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: "Icon" }));
jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));
const mockWebViewProps: Record<string, unknown>[] = [];
jest.mock("@/lib/webView", () => ({
  getPreviewWebView: () => ({
    mode: "rnc",
    Component: (props: Record<string, unknown>) => {
      mockWebViewProps.push(props);
      const { View: MockView } = jest.requireActual<typeof import("react-native")>("react-native");
      return <MockView testID="pdf-webview" />;
    },
  }),
}));

it("gives the page preview a width of its own that nothing between shrinks", async () => {
  const { findByTestId } = await render(<ChatMessagePdf attachmentId="doc" fileName="lease-notes.pdf" />);
  // The page picture is for sight (the card above names and opens it); look inside hidden views.
  // A sent message's column is aligned to the end, so the preview needs its own width; and
  // react-native-webview's container takes its width from its parent's alignItems.
  // Either one left the page 0 wide: an empty box under the card.
  let node = (await findByTestId("pdf-webview", { includeHiddenElements: true })).parent;
  let width: unknown;
  while (node && width === undefined) {
    const style = StyleSheet.flatten(node.props.style) ?? {};
    expect(style.alignItems === undefined || style.alignItems === "stretch").toBe(true);
    width = typeof style.width === "number" ? style.width : undefined;
    node = node.parent;
  }
  expect(width).toBeGreaterThan(0);
});

it("gives a screen reader one way in: the named card, not the unnamed page picture too", async () => {
  const { getAllByRole, findByTestId, queryByTestId } = await render(
    <ChatMessagePdf attachmentId="doc" fileName="lease-notes.pdf" />,
  );
  await findByTestId("pdf-webview", { includeHiddenElements: true });
  expect(queryByTestId("pdf-webview")).toBeNull();
  expect(getAllByRole("button").map((button) => button.props.accessibilityLabel)).toEqual([
    "chat.pdf_open_a11y",
  ]);
});

it("keeps the preview's own navigation guard: the card adds none of its own", async () => {
  const { findByTestId } = await render(<ChatMessagePdf attachmentId="doc" fileName="lease-notes.pdf" />);
  await findByTestId("pdf-webview", { includeHiddenElements: true });
  const props = mockWebViewProps[mockWebViewProps.length - 1]!;
  expect(props.onShouldStartLoadWithRequest).toBe(mockPdfGuard);
  expect(props.originWhitelist).toEqual(["*"]);
});

// The viewer's Share showed the failure's English as it came, in every language.
it.each([
  ["no answer", serverUnreachableError(), "chat.error_unreachable"],
  ["no connection", new TypeError("Network request failed"), "chat.error_unreachable"],
  ["a file the phone could not open", new Error("Could not open this attachment."), "chat.pdf_export_failed"],
  ["a build that cannot share files", new SharingUnavailableError(), "common.share_needs_update"],
])("words a share that failed with %s in the phone's language", async (_label, failure, key) => {
  jest.mocked(downloadChatAttachment).mockRejectedValueOnce(failure);
  await render(<ChatMessagePdf attachmentId="doc" fileName="lease-notes.pdf" />);
  await act(async () => { await mockShare?.(); });
  expect(alertDialog).toHaveBeenLastCalledWith({ title: "common.download_failed", message: key });
});
