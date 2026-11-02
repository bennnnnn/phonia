import { StyleSheet } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";

import { AttachmentLightboxChrome } from "@/features/attachments/components/AttachmentLightboxChrome";
import { lightTheme as mockLightTheme, withAlpha } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

const actions = {
  onClose: jest.fn(),
  onShare: jest.fn(),
  onDownload: jest.fn(),
  onToggleOverflow: jest.fn(),
  onCloseOverflow: jest.fn(),
  onUseInChat: jest.fn(),
  onOpenChat: jest.fn(),
  onDelete: jest.fn(),
};

it("derives attachment chrome from media theme tokens", async () => {
  const props = {
    visible: true,
    overflowOpen: false,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
    busy: null,
    canShare: true,
    showUseInChat: true,
    showOpenChat: false,
    showDelete: false,
    ...actions,
  } as const;
  const ui = await render(<AttachmentLightboxChrome {...props} />);

  expect(StyleSheet.flatten(ui.getByLabelText("preview.close").props.style))
    .toMatchObject({
      backgroundColor: withAlpha(mockLightTheme.onMedia, 0.18),
    });

});

it("opens the overflow as the shared popover and runs the picked row", async () => {
  const props = {
    visible: true,
    overflowOpen: true,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
    busy: null,
    canShare: true,
    showUseInChat: true,
    showOpenChat: true,
    showDelete: true,
    ...actions,
  } as const;
  const ui = await render(<AttachmentLightboxChrome {...props} />);
  const hidden = { includeHiddenElements: true };
  const rows = ui.getAllByRole("menuitem", hidden).map((row) => row.props.accessibilityLabel);
  expect(rows).toEqual(["gallery.use_in_chat", "gallery.open_chat", "common.delete"]);

  await fireEvent.press(ui.getByRole("menuitem", { name: "gallery.open_chat", ...hidden }));
  expect(actions.onCloseOverflow).toHaveBeenCalledTimes(1);
  expect(actions.onOpenChat).toHaveBeenCalledTimes(1);
  expect(actions.onDelete).not.toHaveBeenCalled();
});

it("drops More when it has no rows, and keeps nothing at the bottom", async () => {
  const ui = await render(
    <AttachmentLightboxChrome
      visible
      overflowOpen={false}
      insets={{ top: 0, right: 0, bottom: 0, left: 0 }}
      busy={null}
      canShare
      showUseInChat={false}
      showOpenChat={false}
      showDelete={false}
      {...actions}
    />,
  );
  expect(ui.queryByLabelText("preview.more_a11y")).toBeNull();
  expect(ui.getByLabelText("common.download")).toBeTruthy();
  expect(ui.getByRole("button", { name: "preview.share" })).toHaveStyle({
    backgroundColor: mockLightTheme.onMedia,
  });
});

it("spins Share while the file is prepared and blocks Download meanwhile", async () => {
  const ui = await render(
    <AttachmentLightboxChrome
      visible
      overflowOpen={false}
      insets={{ top: 0, right: 0, bottom: 0, left: 0 }}
      busy="share"
      canShare
      showUseInChat
      showOpenChat={false}
      showDelete
      {...actions}
    />,
  );
  expect(ui.getByRole("button", { name: "preview.share" }).props.accessibilityState).toEqual({ disabled: true, busy: true });
  expect(ui.getByLabelText("common.download").props.accessibilityState).toMatchObject({ disabled: true });
});
