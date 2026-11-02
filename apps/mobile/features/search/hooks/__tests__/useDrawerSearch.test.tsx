import React from "react";
import { Text, type TextInput } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useDrawerSearch } from "@/features/search/hooks/useDrawerSearch";
import { api, type SearchResult } from "@/lib/api";

let mockSession = 0;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/lib/api", () => ({ api: { search: jest.fn() } }));
const search = api.search as jest.Mock;
const hit = (id: string): SearchResult => ({ match_type: "message", chat_id: "chat", chat_title: "Title", message_id: id, content: id, role: "user", created_at: "2026-09-04T00:00:00Z" });
const page = (ids: string[], hasMore = false) => ({ items: ids.map(hit), next_cursor: hasMore ? `after-${ids.at(-1) ?? "none"}` : null });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
let current: ReturnType<typeof useDrawerSearch>;
function Probe({ token = "token", open = true }: { token?: string | null; open?: boolean }) {
  const result = useDrawerSearch({ token, isDrawerOpen: open });
  React.useLayoutEffect(() => { current = result; });
  return <Text>{result.searchResults.map((result) => result.message_id).join(",")}</Text>;
}
async function query(text: string) {
  await act(async () => { current.onSearchChange(text); });
  await act(async () => { jest.advanceTimersByTime(300); });
}
async function mount() {
  const view = await render(<Probe />);
  await act(async () => { current.openSearch(); });
  return view;
}
beforeEach(() => { jest.useFakeTimers(); jest.clearAllMocks(); search.mockReset(); mockSession++; });
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers(); });

it("clears account A results immediately and drops its late page when account B signs in", async () => {
  search.mockResolvedValueOnce(page(["a"], true));
  const view = await mount();
  await query("alpha");
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  let request!: Promise<void>;
  await act(async () => { request = current.loadMore(); });
  mockSession++;
  await view.rerender(<Probe token="account-b" />);
  expect(current.searchOpen).toBe(false);
  expect(current.searchQuery).toBe("");
  expect(current.searchResults).toEqual([]);
  await act(async () => { late.resolve(page(["old-a"], true)); await request; });
  expect(current.searchResults).toEqual([]);
});

it("invalidates the old response as soon as a new query is typed, before debounce", async () => {
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  await mount();
  await query("alpha");
  await act(async () => { current.onSearchChange("beta"); });
  await act(async () => { late.resolve(page(["old-alpha"])); });
  expect(current.searchResults).toEqual([]);
  expect(current.searchLoading).toBe(true);
  expect(search).toHaveBeenCalledTimes(1);
});

it("does not append an old alpha page after alpha-beta-alpha", async () => {
  search.mockResolvedValueOnce(page(["alpha-1"], true));
  await mount();
  await query("alpha");
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  let request!: Promise<void>;
  await act(async () => { request = current.loadMore(); });
  search.mockResolvedValueOnce(page(["beta"]));
  await query("beta");
  search.mockResolvedValueOnce(page(["alpha-new"], true));
  await query("alpha");
  await act(async () => { late.resolve(page(["old-alpha-page"], true)); await request; });
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["alpha-new"]);
});

it("deduplicates consecutive load-more taps before React rerenders", async () => {
  search.mockResolvedValueOnce(page(["first"], true));
  await mount();
  await query("alpha");
  const next = deferred<ReturnType<typeof page>>();
  search.mockReturnValue(next.promise);
  let requests!: Promise<void>[];
  await act(async () => { requests = [current.loadMore(), current.loadMore()]; });
  await act(async () => { next.resolve(page(["second"], true)); await Promise.all(requests); });
  expect(search).toHaveBeenCalledTimes(2);
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["first", "second"]);
});

it("keeps successful pages and retries a failed page at the same cursor", async () => {
  search.mockResolvedValueOnce(page(["first"], true));
  await mount();
  await query("alpha");
  search.mockRejectedValueOnce(new Error("offline"));
  await act(async () => { await current.loadMore(); });
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["first"]);
  expect(current.loadingMoreError).toBe(true);
  expect(current.searchError).toBe(false);
  search.mockResolvedValueOnce(page(["second"], true));
  await act(async () => { await current.loadMore(); });
  expect(search.mock.calls[1][4]).toBe("after-first");
  expect(search.mock.calls[2][4]).toBe("after-first");
  expect(current.loadingMoreError).toBe(false);
});

it("retries a failed first page without requiring the user to edit the query", async () => {
  search.mockRejectedValueOnce(new Error("offline"));
  await mount();
  await query("alpha");
  expect(current.searchError).toBe(true);
  search.mockResolvedValueOnce(page(["recovered"]));
  await act(async () => { current.retrySearch(); });
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["recovered"]);
  expect(current.searchError).toBe(false);
});

it("preserves search and an inflight response through ordinary token refresh", async () => {
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  const view = await mount();
  await query("alpha");
  await view.rerender(<Probe token="rotated-token" />);
  await act(async () => { late.resolve(page(["same-account"])); });
  expect(current.searchOpen).toBe(true);
  expect(current.searchQuery).toBe("alpha");
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["same-account"]);
  expect(search).toHaveBeenCalledTimes(1);
});

it("aborts pagination and ignores its completion when the drawer closes", async () => {
  search.mockResolvedValueOnce(page(["first"], true));
  const view = await mount();
  await query("alpha");
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  let request!: Promise<void>;
  await act(async () => { request = current.loadMore(); });
  const signal = search.mock.calls[1][3]?.signal as AbortSignal | undefined;
  await view.rerender(<Probe open={false} />);
  expect(signal?.aborted).toBe(true);
  await act(async () => { late.resolve(page(["late"], true)); await request; });
  expect(current.searchResults).toEqual([]);
});

it("cancels a queued search focus when closing before the next animation frame", async () => {
  const view = await render(<Probe />);
  const focus = jest.fn();
  current.searchInputRef.current = { focus } as unknown as TextInput;
  await act(async () => { current.openSearch(); current.closeSearch(); });
  await act(async () => { jest.advanceTimersByTime(20); });
  expect(focus).not.toHaveBeenCalled();
  await view.unmount();
});

it("does not request empty, short or over-limit queries", async () => {
  search.mockResolvedValue(page([]));
  await mount();
  for (const value of ["   ", " a ", " ab ", "x".repeat(201)]) await query(value);
  expect(search).not.toHaveBeenCalled();
  expect(current.hasSearchQuery).toBe(false);
  expect(current.searchLoading).toBe(false);
});

it("deduplicates overlapping rows and reads on from the server's cursor", async () => {
  search.mockResolvedValueOnce(page(["first", "second"], true));
  await mount();
  await query("alpha");
  search.mockResolvedValueOnce(page(["second", "third"], true));
  await act(async () => { await current.loadMore(); });
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["first", "second", "third"]);
  search.mockResolvedValueOnce(page(["fourth"], true));
  await act(async () => { await current.loadMore(); });
  expect(search.mock.calls[2][4]).toBe("after-third");
});

it("stops after an empty page even when the server still says more rows follow", async () => {
  search.mockResolvedValueOnce(page(["first"], true));
  await mount();
  await query("alpha");
  search.mockResolvedValueOnce(page([], true));
  await act(async () => { await current.loadMore(); });
  expect(current.hasMore).toBe(false);
  await act(async () => { await current.loadMore(); });
  expect(search).toHaveBeenCalledTimes(2);
});


it("stops when the server's cursor does not move past the page it sent", async () => {
  search.mockResolvedValueOnce(page(["first"], true));
  await mount();
  await query("alpha");
  search.mockResolvedValueOnce(page(["first"], true));
  await act(async () => { await current.loadMore(); });
  expect(current.hasMore).toBe(false);
});

it.each(["query", "account", "drawer", "unmount"])("invalidates retained result callbacks after %s changes", async (change) => {
  search.mockResolvedValue(page(["first"], true));
  const view = await mount();
  await query("alpha");
  const retained = current.isCurrentSearch;
  const retainedLoad = current.loadMore;
  if (change === "query") {
    await query("beta");
    await query("alpha");
  } else if (change === "account") {
    mockSession++;
    expect(retained()).toBe(false);
    await view.rerender(<Probe token="account-b" />);
  } else if (change === "drawer") {
    await view.rerender(<Probe open={false} />);
    await view.rerender(<Probe open />);
    await act(async () => { current.openSearch(); });
    await query("alpha");
  } else await view.unmount();
  expect(retained()).toBe(false);
  const calls = search.mock.calls.length;
  await act(async () => { await retainedLoad(); });
  expect(search).toHaveBeenCalledTimes(calls);
});

it("does not clear the new page spinner when an old page finally resolves", async () => {
  search.mockResolvedValueOnce(page(["alpha"], true));
  await mount();
  await query("alpha");
  const oldPage = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(oldPage.promise);
  let oldRequest!: Promise<void>;
  await act(async () => { oldRequest = current.loadMore(); });
  search.mockResolvedValueOnce(page(["beta"], true));
  await query("beta");
  const newPage = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(newPage.promise);
  let newRequest!: Promise<void>;
  await act(async () => { newRequest = current.loadMore(); });
  await act(async () => { oldPage.resolve(page(["old"], true)); await oldRequest; });
  expect(current.loadingMore).toBe(true);
  await act(async () => { newPage.resolve(page(["new"], true)); await newRequest; });
  expect(current.loadingMore).toBe(false);
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["beta", "new"]);
});

it("cancels its queued debounce timer on unmount", async () => {
  const view = await mount();
  const schedule = jest.spyOn(globalThis, "setTimeout");
  const cancel = jest.spyOn(globalThis, "clearTimeout");
  await act(async () => { current.onSearchChange("alpha"); });
  const debounceIndex = schedule.mock.calls.findIndex((call) => call[1] === 300);
  const debounce = schedule.mock.results[debounceIndex].value;
  await view.unmount();
  expect(cancel).toHaveBeenCalledWith(debounce);
  await act(async () => { jest.advanceTimersByTime(400); });
  expect(search).not.toHaveBeenCalled();
});

it("aborts the active first-page request on unmount", async () => {
  const late = deferred<ReturnType<typeof page>>();
  search.mockReturnValueOnce(late.promise);
  const view = await mount();
  await query("alpha");
  const signal = search.mock.calls[0][3].signal as AbortSignal;
  const retained = current.isCurrentSearch;
  await view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => { late.resolve(page(["late"])); });
  expect(retained()).toBe(false);
});

it("uses the refreshed token for a search still waiting in debounce", async () => {
  search.mockResolvedValueOnce(page(["new-token"]));
  const view = await mount();
  await act(async () => { current.onSearchChange("alpha"); });
  await view.rerender(<Probe token="refreshed-token" />);
  await act(async () => { jest.advanceTimersByTime(300); });
  expect(search.mock.calls[0][0]).toBe("refreshed-token");
  expect(current.searchResults.map((result) => result.message_id)).toEqual(["new-token"]);
});


it("cancels its queued focus frame on unmount", async () => {
  const view = await render(<Probe />);
  const focus = jest.fn();
  current.searchInputRef.current = { focus } as unknown as TextInput;
  const schedule = jest.spyOn(globalThis, "requestAnimationFrame");
  const cancel = jest.spyOn(globalThis, "cancelAnimationFrame");
  let focusFrame!: number;
  await act(async () => {
    current.openSearch();
    focusFrame = schedule.mock.results[schedule.mock.results.length - 1].value;
  });
  await view.unmount();
  expect(cancel).toHaveBeenCalledWith(focusFrame);
  await act(async () => { jest.advanceTimersByTime(20); });
  expect(focus).not.toHaveBeenCalled();
});
