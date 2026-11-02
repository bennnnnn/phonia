import type { Message } from "@/lib/api";
import type { ChatScreenMenuSheetsProps } from "@/features/chat/components/ChatScreenMenuSheets";

/** What the chat's actions (useChatActions) hold for the header menu and its sheets. */
type MenuActions = {
  menuVisible: boolean;
  setMenuVisible: (visible: boolean) => void;
  onShareFromMenu: () => void;
  onExportPdfFromMenu: () => void;
  onRenameFromMenu: () => void;
  onTogglePinFromMenu: () => void;
  onToggleArchiveFromMenu: () => void;
  onDeleteFromMenu: () => void;
  renameVisible: boolean;
  renameText: string;
  setRenameText: (text: string) => void;
  setRenameVisible: (visible: boolean) => void;
  confirmRename: () => Promise<unknown>;
  shareVisible: boolean;
  closeShare: () => void;
  loadTranscriptMessages: () => Promise<Message[]>;
};

/** The menu, rename and share sheets' props from the chat's actions and the chat on screen;
 * the header's anchor ref is passed on its own, never read while rendering. */
export function chatMenuSheetProps(
  actions: MenuActions,
  chat: Pick<ChatScreenMenuSheetsProps, "chatTitle" | "pinned" | "archived">,
): Omit<ChatScreenMenuSheetsProps, "menuAnchorRef"> {
  return {
    ...chat,
    menuVisible: actions.menuVisible,
    onCloseMenu: () => actions.setMenuVisible(false),
    onShare: actions.onShareFromMenu,
    onExportPdf: actions.onExportPdfFromMenu,
    onRename: actions.onRenameFromMenu,
    onTogglePin: actions.onTogglePinFromMenu,
    onToggleArchive: actions.onToggleArchiveFromMenu,
    onDelete: actions.onDeleteFromMenu,
    renameVisible: actions.renameVisible,
    renameText: actions.renameText,
    onRenameTextChange: actions.setRenameText,
    onCloseRename: () => actions.setRenameVisible(false),
    onConfirmRename: () => void actions.confirmRename(),
    shareVisible: actions.shareVisible,
    onCloseShare: actions.closeShare,
    loadShareMessages: actions.loadTranscriptMessages,
  };
}
