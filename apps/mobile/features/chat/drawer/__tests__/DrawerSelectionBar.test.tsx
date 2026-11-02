import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import { DrawerSelectionBar } from "@/features/chat/drawer/DrawerSelectionBar";
import type { ConversationListStyles } from "@/features/chat/drawer/conversationListStyles";
import type { Theme } from "@/lib/theme";

jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

it("deletes the selection, and offers nothing with none selected", async () => {
  const remove = jest.fn();
  const props = { styles: {} as ConversationListStyles, theme: {} as Theme, paddingBottom: 0, onDelete: remove };
  const view = await render(<DrawerSelectionBar {...props} selectedCount={2} />);
  const deleteButton = view.getByRole("button", { name: "drawer.bulk_delete" });
  expect(deleteButton).not.toBeDisabled();
  await fireEvent.press(deleteButton);
  expect(remove).toHaveBeenCalledTimes(1);
  await view.rerender(<DrawerSelectionBar {...props} selectedCount={0} />);
  expect(view.getByRole("button", { name: "drawer.bulk_delete" })).toBeDisabled();
});
