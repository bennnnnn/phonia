import { todosApi } from "@/features/todos/api";
import { request, requestRevalidated } from "@/lib/api/client";
import type { Todo } from "@/lib/api/types";
jest.mock("@/lib/api/client", () => ({ request: jest.fn(), requestRevalidated: jest.fn() }));
const page = Array.from({ length: 1000 }, (_, index) => ({ id: String(index) } as Todo));
const cursor = "00000000-0000-0000-0000-000000000999";
beforeEach(() => jest.resetAllMocks());

it("loads every page before returning the authoritative list", async () => {
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: page, next_cursor: cursor })
    .mockResolvedValueOnce({ items: [{ id: "last" }], next_cursor: null });
  const options = { signal: new AbortController().signal };
  expect((await todosApi.listTodos("token", options)).todos).toHaveLength(1001);
  // Open rows and the last 30 days' completed ones (NET-16).
  expect(requestRevalidated).toHaveBeenNthCalledWith(1, "/todos/page?limit=1000&completed_days=30", "token", options);
  expect(requestRevalidated).toHaveBeenNthCalledWith(
    2, `/todos/page?limit=1000&completed_days=30&cursor=${cursor}`, "token", options,
  );
});

it("rejects a partial list when a later page fails", async () => {
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: page, next_cursor: cursor })
    .mockRejectedValueOnce(new Error("offline"));
  await expect(todosApi.listTodos("token")).rejects.toThrow("offline");
});

it("follows the cursor even when concurrent deletions leave an empty page", async () => {
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: [], next_cursor: cursor })
    .mockResolvedValueOnce({ items: [{ id: "remaining" }], next_cursor: null });
  await expect(todosApi.listTodos("token")).resolves.toEqual({ todos: [{ id: "remaining" }], olderCompleted: false });
  expect(requestRevalidated).toHaveBeenCalledTimes(2);
});

it("stops on a terminal full page without an extra request", async () => {
  jest.mocked(requestRevalidated).mockResolvedValueOnce({ items: page, next_cursor: null });
  await expect(todosApi.listTodos("token")).resolves.toEqual({ todos: page, olderCompleted: false });
  expect(requestRevalidated).toHaveBeenCalledTimes(1);
});

it("rejects a looping cursor before returning incomplete data", async () => {
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: [{ id: "first" }], next_cursor: cursor })
    .mockResolvedValueOnce({ items: [], next_cursor: "00000000-0000-0000-0000-000000001000" })
    .mockResolvedValueOnce({ items: [], next_cursor: cursor });
  await expect(todosApi.listTodos("token")).rejects.toThrow("Todo pagination did not advance");
  expect(requestRevalidated).toHaveBeenCalledTimes(3);
});

it("propagates cancellation from a later page without returning a partial list", async () => {
  const error = Object.assign(new Error("Aborted"), { name: "AbortError" });
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: page, next_cursor: cursor })
    .mockRejectedValueOnce(error);
  await expect(todosApi.listTodos("token")).rejects.toBe(error);
});

it("says when older completed to-dos were left out, and reads every row on request", async () => {
  jest.mocked(requestRevalidated)
    .mockResolvedValueOnce({ items: [{ id: "open" }], next_cursor: null, older_completed: true })
    .mockResolvedValueOnce({ items: [{ id: "open" }, { id: "old" }], next_cursor: null, older_completed: false });
  await expect(todosApi.listTodos("token")).resolves.toEqual({ todos: [{ id: "open" }], olderCompleted: true });
  await expect(todosApi.listTodos("token", { allCompleted: true })).resolves.toEqual({
    todos: [{ id: "open" }, { id: "old" }],
    olderCompleted: false,
  });
  expect(jest.mocked(requestRevalidated).mock.calls[1][0]).toBe("/todos/page?limit=1000");
});

it("omits the unsupported project field from normal reminder creation", async () => {
  jest.mocked(request).mockResolvedValue({ id: "created" });
  await todosApi.createTodo("token", "Flight", "General", { dueAt: "2026-09-05T12:00:00Z" });
  const [path, token, init] = jest.mocked(request).mock.calls[0];
  expect(path).toBe("/todos");
  expect(token).toBe("token");
  expect(JSON.parse(init!.body as string)).toEqual({ content: "Flight", topic: "General", chat_id: null, due_at: "2026-09-05T12:00:00Z" });
});

it("creates a plain to-do without a due date", async () => {
  jest.mocked(request).mockResolvedValue({ id: "created" });
  await todosApi.createTodo("token", "Buy milk");
  const [, , init] = jest.mocked(request).mock.calls[0];
  expect(JSON.parse(init!.body as string)).toEqual({
    content: "Buy milk",
    topic: "General",
    chat_id: null,
  });
});

it("sends an explicit null when removing a date", async () => {
  jest.mocked(request).mockResolvedValue({ id: "updated" });
  await todosApi.updateTodo("token", "todo-1", {
    due_at: null,
    recurrence_rule: null,
  });
  const [, , init] = jest.mocked(request).mock.calls[0];
  expect(JSON.parse(init!.body as string)).toEqual({
    due_at: null,
    recurrence_rule: null,
  });
});
