import { chatMenuSheetProps } from "@/features/chat/components/chatMenuSheetProps";

/** The menu sheets get what the chat's actions hold, as ChatScreen wired them by hand. */
describe("the chat menu sheets' props", () => {
  const actions = {
    menuVisible: true,
    setMenuVisible: jest.fn(),
    onShareFromMenu: jest.fn(),
    onExportPdfFromMenu: jest.fn(),
    onRenameFromMenu: jest.fn(),
    onTogglePinFromMenu: jest.fn(),
    onToggleArchiveFromMenu: jest.fn(),
    onDeleteFromMenu: jest.fn(),
    renameVisible: false,
    renameText: "Old title",
    setRenameText: jest.fn(),
    setRenameVisible: jest.fn(),
    confirmRename: jest.fn(async () => true),
    shareVisible: true,
    closeShare: jest.fn(),
    loadTranscriptMessages: jest.fn(async () => []),
  };

  it("passes the actions through and closes what it opened", () => {
    const props = chatMenuSheetProps(actions, { chatTitle: "Chat", pinned: true, archived: false });
    expect(props).toMatchObject({
      chatTitle: "Chat", pinned: true, archived: false, menuVisible: true, renameVisible: false,
      renameText: "Old title", shareVisible: true, onShare: actions.onShareFromMenu,
      onExportPdf: actions.onExportPdfFromMenu, onRename: actions.onRenameFromMenu,
      onTogglePin: actions.onTogglePinFromMenu, onToggleArchive: actions.onToggleArchiveFromMenu,
      onDelete: actions.onDeleteFromMenu, onRenameTextChange: actions.setRenameText,
      onCloseShare: actions.closeShare, loadShareMessages: actions.loadTranscriptMessages,
    });
    props.onCloseMenu();
    props.onCloseRename();
    props.onConfirmRename();
    expect(actions.setMenuVisible).toHaveBeenCalledWith(false);
    expect(actions.setRenameVisible).toHaveBeenCalledWith(false);
    expect(actions.confirmRename).toHaveBeenCalledTimes(1);
  });
});
