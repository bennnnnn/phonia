import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useDrawerChatSelection } from "@/features/chat/drawer/useDrawerChatSelection";
import type { Chat } from "@/lib/api";
let mockSession = 0;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
const chats = [{ id: "first" }, { id: "second", archived: true }] as Chat[];
let selection: ReturnType<typeof useDrawerChatSelection>;
function Probe({ listedChats = chats, selectableChats = chats.slice(0, 1), token = "token",
  isDrawerOpen = true }: {
  listedChats?: Chat[]; selectableChats?: Chat[]; token?: string; isDrawerOpen?: boolean;
}) {
  const value = useDrawerChatSelection({ listedChats, selectableChats, token, isDrawerOpen });
  React.useLayoutEffect(() => { selection = value; });
  return <Text>{value.selectedCount}</Text>;
}
beforeEach(() => { mockSession = 0; });

it("only counts selected chats still listed and recovers selection after an optimistic rollback", async () => {
  const view = await render(<Probe />);
  await act(async () => { selection.enterSelectionMode("first"); });
  await view.rerender(<Probe listedChats={[chats[1]]} />);
  expect(selection.selectedCount).toBe(0);
  expect(selection.selectedIds.has("first")).toBe(false);
  await view.rerender(<Probe />);
  expect(selection.selectedCount).toBe(1);
  expect(selection.selectedIds.has("first")).toBe(true);
});

it("clears selection on account change but keeps it through a token refresh", async () => {
  const view = await render(<Probe />);
  await act(async () => { selection.enterSelectionMode("first"); });
  await view.rerender(<Probe token="refreshed" />);
  expect(selection.selectedCount).toBe(1);
  mockSession++;
  await view.rerender(<Probe token="other-account" />);
  expect(selection.selectionMode).toBe(false);
  expect(selection.selectedCount).toBe(0);
});

it("does not let an old batch completion clear a newer selection in the same drawer", async () => {
  await render(<Probe />);
  await act(async () => { selection.enterSelectionMode("first"); });
  const oldComplete = selection.exitSelectionMode;
  await act(async () => { selection.exitSelectionMode(); });
  await act(async () => { selection.enterSelectionMode("second"); });
  await act(async () => { oldComplete(); });
  expect(selection.selectionMode).toBe(true);
  expect([...selection.selectedIds]).toEqual(["second"]);
});

it("rejects retained selection callbacks after the drawer closes and reopens", async () => {
  const view = await render(<Probe />);
  const oldEnter = selection.enterSelectionMode;
  await view.rerender(<Probe isDrawerOpen={false} />);
  await view.rerender(<Probe />);
  await act(async () => { oldEnter("first"); });
  expect(selection.selectionMode).toBe(false);
  expect(selection.selectedCount).toBe(0);
});

it("selects all of what is on screen, never the archived chats", async () => {
  await render(<Probe />);
  await act(async () => { selection.enterSelectionMode(); });
  await act(async () => { selection.selectAllListed(); });
  expect([...selection.selectedIds]).toEqual(["first"]);
});
