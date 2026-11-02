import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import { DrawerSearchLoadMore, DrawerSearchResultRow, DrawerSearchResultsChrome } from "@/features/search/components/DrawerSearchResults";
import { DrawerListHeader } from "@/features/chat/drawer/DrawerListHeader";
import type { SearchResult } from "@/lib/api";
import { DrawerChatFlashList, type DrawerChatListItem } from "@/features/chat/drawer/DrawerChatFlashList";
import { emptyChatList } from "@/features/chat/model/listSections";

jest.mock("@/features/chat/drawer/drawer", () => ({ isChatTitleGenerating: () => false }));
jest.mock("@shopify/flash-list", () => ({ FlashList: ({ data, renderItem }: {
  data: DrawerChatListItem[]; renderItem: (args: { item: DrawerChatListItem }) => React.ReactNode;
}) => {
  const React = jest.requireActual<typeof import("react")>("react");
  return React.createElement(React.Fragment, null, ...data.map((item) =>
    React.createElement(React.Fragment, { key: item.key }, renderItem({ item }))));
} }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual<typeof import("@/lib/theme")>("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});
jest.mock("@/ui/feedback/SkeletonLoader", () => ({ SkeletonList: () => null }));

it("offers first-page search retry without editing the query", async () => {
  const retry = jest.fn();
  const view = await render(<DrawerSearchResultsChrome hasSearchQuery searchLoading={false} searchError
    resultCount={0} onRetry={retry} />);
  await fireEvent.press(view.getByRole("button", { name: "common.retry" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

it("shows a retry after a pagination failure", async () => {
  const loadMore = jest.fn();
  const view = await render(<DrawerSearchLoadMore loadingMoreError onLoadMore={loadMore} />);
  expect(view.getByText("common.error")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "common.retry" }));
  expect(loadMore).toHaveBeenCalledTimes(1);
});

it("does not present unrelated chat-list errors while viewing successful search results", async () => {
  const view = await render(<DrawerListHeader loading={false} error activeChatCount={0} searchOpen
    onRetry={jest.fn()} onRetrySearch={jest.fn()} hasSearchQuery searchLoading={false} searchError={false} searchResultCount={1} />);
  expect(view.queryByText("drawer.cant_reach")).toBeNull();
  expect(view.getByText("search.results")).toBeTruthy();
});

it("keeps snippets as literal text and exposes result navigation as a button", async () => {
  const open = jest.fn();
  const content = '<script>alert("hi")</script> **literal** [click](https://example.com)';
  const result: SearchResult = { chat_id: "chat", message_id: "message", chat_title: "A title",
    content, match_type: "message", role: "user", created_at: "2026-01-01" };
  const view = await render(<DrawerSearchResultRow result={result} title="A title" onOpenChat={open} />);
  expect(view.getByText(content)).toBeTruthy();
  await fireEvent.press(view.getByRole("button"));
  expect(open).toHaveBeenCalledWith("chat", "message");
});

it("shows the existing hint for queries below the minimum length", async () => {
  const view = await render(<DrawerSearchResultsChrome hasSearchQuery={false} searchLoading={false}
    searchError={false} resultCount={0} onRetry={jest.fn()} />);
  expect(view.getByText("search.empty")).toBeTruthy();
  expect(view.queryByText("search.no_results")).toBeNull();
});

it("wires search rows to the guarded result action and keeps the failed page retry after existing results", async () => {
  const guardedOpen = jest.fn();
  const ordinaryOpen = jest.fn();
  const retryPage = jest.fn();
  const result: SearchResult = { chat_id: "chat", message_id: "message", chat_title: "A title", content: "Existing result",
    match_type: "message", role: "user", created_at: "2026-01-01" };
  const view = await render(<DrawerChatFlashList groups={emptyChatList()} activeChatCount={0} loading={false} error={false}
    isSectionCollapsed={() => false} toggleSectionCollapsed={jest.fn()} onOpenChat={ordinaryOpen} onOpenSearchResult={guardedOpen}
    onShowRowMenu={jest.fn()} listHeader={<></>} contentPaddingTop={0} contentPaddingBottom={0} refreshing={false}
    onRefresh={jest.fn()} searchOpen searchResults={[result]} searchHasMore searchLoadingMoreError onSearchLoadMore={retryPage} />);
  await fireEvent.press(view.getByText("Existing result"));
  await fireEvent.press(view.getByRole("button", { name: "common.retry" }));
  expect(guardedOpen).toHaveBeenCalledWith("chat", "message");
  expect(ordinaryOpen).not.toHaveBeenCalled();
  expect(retryPage).toHaveBeenCalledTimes(1);
});

it("tags a hit in an archived chat, which search used to skip", async () => {
  const result: SearchResult = { chat_id: "chat", message_id: "message", chat_title: "Old trip",
    content: "the pelican", match_type: "message", role: "user", created_at: "2026-01-01", archived: true };
  const view = await render(<DrawerSearchResultRow result={result} title="Old trip" onOpenChat={jest.fn()} />);
  expect(view.getByText("search.archived_tag")).toBeTruthy();
  const live = await render(<DrawerSearchResultRow result={{ ...result, archived: false }} title="Old trip"
    onOpenChat={jest.fn()} />);
  expect(live.queryByText("search.archived_tag")).toBeNull();
});

it("offers more archived chats under the archived section, and retries a failed page", async () => {
  const more = jest.fn();
  const archivedChat = { id: "a1", title: "Archived one", pinned: false, archived: true,
    created_at: "2025-01-01T00:00:00Z", updated_at: "2025-01-01T00:00:00Z", model: "free-chat" };
  const groups = { ...emptyChatList(), archived: [archivedChat], archived_next_cursor: "after-a1" };
  const props = { groups, activeChatCount: 0, loading: false, error: false,
    isSectionCollapsed: () => false, toggleSectionCollapsed: jest.fn(), onOpenChat: jest.fn(),
    onOpenSearchResult: jest.fn(), onShowRowMenu: jest.fn(), listHeader: <></>, contentPaddingTop: 0,
    contentPaddingBottom: 0, refreshing: false, onRefresh: jest.fn(), onLoadMoreArchived: more };
  const view = await render(<DrawerChatFlashList {...props} />);
  await fireEvent.press(view.getByRole("button", { name: "drawer.archived_show_more" }));
  expect(more).toHaveBeenCalledTimes(1);

  const failed = await render(<DrawerChatFlashList {...props} archivedPaging="failed" />);
  await fireEvent.press(failed.getByRole("button", { name: "common.retry" }));
  expect(more).toHaveBeenCalledTimes(2);

  const all = await render(<DrawerChatFlashList {...props} onLoadMoreArchived={undefined} />);
  expect(all.queryByRole("button", { name: "drawer.archived_show_more" })).toBeNull();
});
