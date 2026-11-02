import { render } from "@testing-library/react-native";

import { AttachmentTextViewer } from "@/features/attachments/components/AttachmentTextViewer";
import { fetchAttachmentBytes } from "@/features/attachments/model/fetchAttachmentBytes";
import { lightTheme as mockLightTheme } from "@/lib/theme";

// One object, as the provider keeps it: a new getter per render re-runs every effect.
const mockAccountSession = { account: "user-1:0", getToken: () => "tok" };
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockAccountSession,
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuthToken: () => "tok",
}));
jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: ({ attachmentId }: { attachmentId?: string }) =>
    `http://test.local/${attachmentId}`,
}));
jest.mock("@/features/attachments/model/fetchAttachmentBytes", () => ({
  fetchAttachmentBytes: jest.fn(),
}));
jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

describe("AttachmentTextViewer", () => {
  it("shows the file text for reading", async () => {
    const encoded = new TextEncoder().encode("hello notes");
    jest.mocked(fetchAttachmentBytes).mockResolvedValueOnce(
      encoded.buffer.slice(encoded.byteOffset, encoded.byteOffset + encoded.byteLength),
    );
    const { findByText } = await render(
      <AttachmentTextViewer
        visible
        onClose={jest.fn()}
        onShare={jest.fn()}
        attachmentId="notes"
        path="/attachments/notes/file"
        fileName="notes.txt"
      />,
    );
    expect(await findByText("hello notes")).toBeTruthy();
  });

  it("cuts a long name in the middle, spins Share while it is prepared, and has a 1pt toolbar line", async () => {
    jest.mocked(fetchAttachmentBytes).mockReturnValueOnce(new Promise(() => {}));
    const { getByText, getByLabelText } = await render(
      <AttachmentTextViewer
        visible
        sharing
        onClose={jest.fn()}
        onShare={jest.fn()}
        attachmentId="notes"
        fileName="a-very-long-meeting-notes-file.md"
      />,
    );
    const title = getByText("a-very-long-meeting-notes-file.md");
    expect(title.props.ellipsizeMode).toBe("middle");
    expect(getByLabelText("preview.share").props.accessibilityState).toMatchObject({ busy: true });
    expect(title.parent).toHaveStyle({ borderBottomWidth: 1, borderBottomColor: mockLightTheme.border });
  });

  it("stops the download when the viewer closes", async () => {
    jest.mocked(fetchAttachmentBytes).mockReturnValueOnce(new Promise(() => {}));
    const props = { onClose: jest.fn(), onShare: jest.fn(), attachmentId: "notes", fileName: "notes.txt" };
    const view = await render(<AttachmentTextViewer visible {...props} />);
    const signal = jest.mocked(fetchAttachmentBytes).mock.calls.at(-1)![2]!;
    expect(signal.aborted).toBe(false);
    await view.rerender(<AttachmentTextViewer visible={false} {...props} />);
    expect(signal.aborted).toBe(true);
  });
});
