import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import { DrawerSelectionBar } from "@/features/chat/drawer/DrawerSelectionBar";
import type { ConversationListStyles } from "@/features/chat/drawer/conversationListStyles";
import type { Theme } from "@/lib/theme";

jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

it("disables Archive for an archived-only selection while keeping Delete available", async () => {
  const archive = jest.fn();
  const remove = jest.fn();
  const view = await render(<DrawerSelectionBar styles={{} as ConversationListStyles} theme={{} as Theme}
    paddingBottom={0} selectedCount={2} archivableCount={0} onArchive={archive} onDelete={remove} />);
  const archiveButton = view.getByRole("button", { name: "drawer.bulk_archive" });
  const deleteButton = view.getByRole("button", { name: "drawer.bulk_delete" });
  expect(archiveButton).toBeDisabled();
  expect(deleteButton).not.toBeDisabled();
  await fireEvent.press(archiveButton);
  await fireEvent.press(deleteButton);
  expect(archive).not.toHaveBeenCalled();
  expect(remove).toHaveBeenCalledTimes(1);
});
