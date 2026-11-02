import { fireEvent, render } from "@testing-library/react-native";

import { ChatActionsMenu } from "@/features/chat/components/ChatActionsMenu";

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 47, bottom: 34, left: 0, right: 0 }),
}));

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

const baseProps = {
  visible: true,
  title: "Trip ideas",
  pinned: false,
  archived: false,
  onClose: jest.fn(),
  onShare: jest.fn(),
  onRename: jest.fn(),
  onTogglePin: jest.fn(),
  onToggleArchive: jest.fn(),
  onDelete: jest.fn(),
};

describe("ChatActionsMenu", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders a popover menu under the chat title", async () => {
    const { getByRole, getByText } = await render(<ChatActionsMenu {...baseProps} />);

    expect(getByRole("menuitem", { name: "chat.share" })).toBeTruthy();
    expect(getByText("Trip ideas")).toBeTruthy();
  });

  it("dismisses when the page behind is tapped", async () => {
    const onClose = jest.fn();
    const { getByTestId } = await render(
      <ChatActionsMenu {...baseProps} onClose={onClose} />,
    );

    await fireEvent.press(getByTestId("chat-actions-menu-scrim", { includeHiddenElements: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes, then runs the action", async () => {
    const order: string[] = [];
    const onClose = jest.fn(() => order.push("close"));
    const onDelete = jest.fn(() => order.push("delete"));
    const { getByRole } = await render(
      <ChatActionsMenu {...baseProps} onClose={onClose} onDelete={onDelete} />,
    );

    await fireEvent.press(getByRole("menuitem", { name: "common.delete" }));
    expect(order).toEqual(["close", "delete"]);
  });

  it("offers Unpin with the pin-off glyph for a pinned chat", async () => {
    const { getByRole } = await render(<ChatActionsMenu {...baseProps} pinned />);
    expect(getByRole("menuitem", { name: "chat.unpin" })).toBeTruthy();
  });

  it("shows Select when onSelectChats is provided", async () => {
    const onSelectChats = jest.fn();
    const { getByText } = await render(
      <ChatActionsMenu {...baseProps} onSelectChats={onSelectChats} />,
    );

    expect(getByText("drawer.select")).toBeTruthy();
    await fireEvent.press(getByText("drawer.select"));
    expect(onSelectChats).toHaveBeenCalledTimes(1);
  });

  it("hides Select when onSelectChats is omitted", async () => {
    const { queryByText } = await render(<ChatActionsMenu {...baseProps} />);
    expect(queryByText("drawer.select")).toBeNull();
  });

  it("does not include Models — that lives in Settings", async () => {
    const { queryByText } = await render(<ChatActionsMenu {...baseProps} />);
    expect(queryByText("settings.model")).toBeNull();
  });

  it("shows Export PDF when onExportPdf is provided", async () => {
    const onExportPdf = jest.fn();
    const { getByText } = await render(
      <ChatActionsMenu {...baseProps} onExportPdf={onExportPdf} />,
    );

    expect(getByText("chat.export_pdf")).toBeTruthy();
    await fireEvent.press(getByText("chat.export_pdf"));
    expect(onExportPdf).toHaveBeenCalledTimes(1);
  });

  it("hides Export PDF when onExportPdf is omitted", async () => {
    const { queryByText } = await render(<ChatActionsMenu {...baseProps} />);
    expect(queryByText("chat.export_pdf")).toBeNull();
  });
});

it("offers Unarchive before Pin for an archived conversation", async () => {
  const view = await render(<ChatActionsMenu {...baseProps} archived />);
  expect(view.queryByText("chat.pin")).toBeNull();
  expect(view.queryByText("chat.unpin")).toBeNull();
  expect(view.getByText("chat.unarchive")).toBeTruthy();
  await view.rerender(<ChatActionsMenu {...baseProps} archived={false} />);
  expect(view.getByText("chat.pin")).toBeTruthy();
});
