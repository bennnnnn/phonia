import React from "react";
import { Alert } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useTodosActions } from "@/features/todos/hooks/useTodosActions";
import { api, type Todo } from "@/lib/api";
import { syncTodoReminders, cancelTodoReminder } from "@/features/todos/model/todoReminders";

let mockSession = 0;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
  ensureLocale: jest.fn(),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/features/todos/model/reminderSeen", () => ({ markReminderIdsSeen: jest.fn(async () => undefined) }));
jest.mock("@/features/todos/model/todoReminders", () => ({
  syncTodoReminders: jest.fn(), cancelTodoReminder: jest.fn(async () => undefined),
}));
jest.mock("@/lib/api", () => ({ api: {
  createTodo: jest.fn(), updateTodo: jest.fn(), deleteTodo: jest.fn(),
} }));
const mockApi = jest.mocked(api);
const A: Todo = { id: "a", content: "Tea", topic: "General", checked: false,
  due_at: "2026-09-04T18:00:00.000Z", sort_order: null, chat_id: null,
  created_at: "2026-09-04", updated_at: "2026-09-04", notify_at: null };
const B: Todo = { ...A, id: "b", content: "Books" };
let rows: Todo[];
let currentView = true;
const setTodos = jest.fn((update: React.SetStateAction<Todo[]>) => {
  rows = typeof update === "function" ? update(rows) : update;
});
const refresh = jest.fn(async () => undefined);
let actions: ReturnType<typeof useTodosActions>;
function Probe({ token = "token" }: { token?: string }) {
  const result = useTodosActions({ token, userId: "user", todos: rows, setTodos,
    refresh, getTodos: () => rows, isCurrentView: () => currentView });
  React.useLayoutEffect(() => { actions = result; });
  return null;
}
function deferred<T>() {
  let resolve!: (value: T) => void; let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function deleteConfirmation() {
  return jest.mocked(Alert.alert).mock.calls.at(-1)?.[2]?.[1]?.onPress as () => Promise<void>;
}
beforeEach(() => {
  jest.clearAllMocks();
  mockSession++;
  rows = [A, B];
  currentView = true;
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

it("keeps an independent successful change when another toggle rolls back", async () => {
  const first = deferred<Todo>();
  mockApi.updateTodo.mockReturnValueOnce(first.promise).mockResolvedValueOnce({ ...B, checked: true });
  await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleToggle(A); });
  await act(async () => { await actions.handleToggle(B); });
  await act(async () => { first.reject(new Error("offline")); await pending; });
  expect(rows).toEqual([A, { ...B, checked: true }]);
  expect(refresh).toHaveBeenCalledWith({ silent: true, force: true, afterPending: true });
});

it("rolls back only a failed deletion using the row current at confirmation", async () => {
  mockApi.deleteTodo.mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  actions.handleDeleteItem(A);
  const confirm = deleteConfirmation();
  rows = [{ ...A, content: "Updated tea" }, { ...B, checked: true }];
  await act(async () => { await confirm(); });
  expect(rows).toContainEqual({ ...A, content: "Updated tea" });
  expect(rows).toContainEqual({ ...B, checked: true });
});

it("toggles the latest row instead of a retained checked value", async () => {
  mockApi.updateTodo.mockResolvedValue(A);
  await render(<Probe />);
  rows = [{ ...A, checked: true }, B];
  await act(async () => { await actions.handleToggle(A); });
  expect(mockApi.updateTodo).toHaveBeenCalledWith("token", A.id, { checked: false });
});

it("keeps a failed create draft open and removes only its temporary row", async () => {
  mockApi.createTodo.mockRejectedValue(new Error("offline"));
  const onCreated = jest.fn();
  await render(<Probe />);
  await act(async () => { await actions.handleCreateTodo("New", new Date(A.due_at!), onCreated); });
  expect(onCreated).not.toHaveBeenCalled();
  expect(rows).toEqual([A, B]);
  expect(actions.savingTodo).toBe(false);
});

it("rejects an invalid date without wedging create", async () => {
  mockApi.createTodo.mockResolvedValue({ ...A, id: "created" });
  await render(<Probe />);
  await act(async () => {
    await expect(actions.handleCreateTodo("Invalid", new Date(NaN), jest.fn())).resolves.toBeUndefined();
  });
  expect(actions.savingTodo).toBe(false);
  expect(mockApi.createTodo).not.toHaveBeenCalled();
  await act(async () => { await actions.handleCreateTodo("Valid", new Date(A.due_at!), jest.fn()); });
  expect(mockApi.createTodo).toHaveBeenCalledTimes(1);
});

it("blocks retained alert confirmation and direct callbacks after a session change", async () => {
  await render(<Probe />);
  actions.handleDeleteItem(A);
  const confirm = deleteConfirmation();
  mockSession++;
  await act(async () => { await confirm(); await actions.handleToggle(A); });
  expect(mockApi.deleteTodo).not.toHaveBeenCalled();
  expect(mockApi.updateTodo).not.toHaveBeenCalled();
  expect(rows).toEqual([A, B]);
});

it("drops stale failures without mutating the next account or showing feedback", async () => {
  const updating = deferred<Todo>();
  mockApi.updateTodo.mockReturnValue(updating.promise);
  const view = await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleToggle(A); });
  mockSession++;
  rows = [{ ...B, id: "new-account" }];
  await view.rerender(<Probe token="new-token" />);
  await act(async () => { updating.reject(new Error("offline")); await pending; });
  expect(rows).toEqual([{ ...B, id: "new-account" }]);
  expect(Alert.alert).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

it("keeps a pending row locked across visits and applies its saved server copy", async () => {
  const updating = deferred<Todo>();
  mockApi.updateTodo.mockReturnValue(updating.promise);
  const first = await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleToggle(A); });
  await first.unmount();
  await render(<Probe />);
  expect(actions.busyTodoIds.has(A.id)).toBe(true);
  await act(async () => { await actions.handleToggle(A); });
  expect(mockApi.updateTodo).toHaveBeenCalledTimes(1);
  await act(async () => { updating.resolve({ ...A, content: "Server tea", checked: true }); await pending; });
  expect(rows[0]).toEqual({ ...A, content: "Server tea", checked: true });
  expect(actions.busyTodoIds.has(A.id)).toBe(false);
});

it("keeps create locked across visits without closing a different visit's sheet", async () => {
  const creating = deferred<Todo>();
  mockApi.createTodo.mockReturnValue(creating.promise);
  const first = await render(<Probe />);
  const onCreated = jest.fn();
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleCreateTodo("New", new Date(A.due_at!), onCreated); });
  await first.unmount();
  await render(<Probe />);
  expect(actions.savingTodo).toBe(true);
  await act(async () => { await actions.handleCreateTodo("Duplicate", new Date(A.due_at!), jest.fn()); });
  expect(mockApi.createTodo).toHaveBeenCalledTimes(1);
  await act(async () => { creating.resolve({ ...A, id: "created" }); await pending; });
  expect(onCreated).not.toHaveBeenCalled();
  expect(actions.savingTodo).toBe(false);
  expect(rows.some((row) => row.id.startsWith("local-todo-"))).toBe(false);
});

it("applies a saved due date even when its original view is no longer active", async () => {
  const updating = deferred<Todo>();
  mockApi.updateTodo.mockReturnValue(updating.promise);
  await render(<Probe />);
  await act(async () => { actions.openTodoEditor(A); });
  let pending!: Promise<boolean>;
  await act(async () => {
    pending = actions.handleUpdateTodo(A, A.content, new Date("2026-09-06T18:00:00.000Z"), null);
  });
  currentView = false;
  await act(async () => { updating.resolve({ ...A, due_at: "2026-09-07T18:00:00.000Z" }); await pending; });
  expect(rows[0].due_at).toBe("2026-09-07T18:00:00.000Z");
});

it("leaves notification syncing to the provider and keeps updater callbacks pure", async () => {
  mockApi.updateTodo.mockResolvedValue({ ...A, checked: true });
  mockApi.deleteTodo.mockResolvedValue(undefined);
  await render(<Probe />);
  await act(async () => { await actions.handleToggle(A); });
  actions.handleDeleteItem(B);
  await act(async () => { await deleteConfirmation()(); });
  expect(syncTodoReminders).not.toHaveBeenCalled();
  expect(cancelTodoReminder).not.toHaveBeenCalled();
});

it("deduplicates a created row already delivered by a list refresh", async () => {
  const creating = deferred<Todo>();
  mockApi.createTodo.mockReturnValue(creating.promise);
  await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleCreateTodo("New", new Date(A.due_at!), jest.fn()); });
  const created = { ...A, id: "created", content: "Server new" };
  rows = [...rows, created];
  await act(async () => { creating.resolve(created); await pending; });
  expect(rows.filter((row) => row.id === created.id)).toEqual([created]);
  expect(rows.some((row) => row.id.startsWith("local-todo-"))).toBe(false);
});

it("retains a pending action through ordinary token refresh", async () => {
  const updating = deferred<Todo>();
  mockApi.updateTodo.mockReturnValue(updating.promise);
  const view = await render(<Probe />);
  let pending!: Promise<void>;
  await act(async () => { pending = actions.handleToggle(A); });
  await view.rerender(<Probe token="refreshed" />);
  expect(actions.busyTodoIds.has(A.id)).toBe(true);
  await act(async () => { updating.resolve({ ...A, checked: true }); await pending; });
  expect(rows[0].checked).toBe(true);
  expect(actions.busyTodoIds.has(A.id)).toBe(false);
});

it("does not save a replaced reminder edit through a retained save callback", async () => {
  await render(<Probe />);
  await act(async () => { actions.openTodoEditor(A); });
  const update = actions.handleUpdateTodo;
  await act(async () => { actions.openTodoEditor(B); });
  await act(async () => {
    await update(A, A.content, new Date(A.due_at!), null);
  });
  expect(mockApi.updateTodo).not.toHaveBeenCalled();
  expect(actions.editingTodo?.id).toBe(B.id);
});

it("applies a change that worked as returned, without reading the list again (NET-16)", async () => {
  mockApi.updateTodo.mockResolvedValueOnce({ ...A, checked: true });
  await render(<Probe />);
  await act(async () => { await actions.handleToggle(A); });
  expect(mockApi.updateTodo).toHaveBeenCalledTimes(1);
  expect(rows).toEqual([{ ...A, checked: true }, B]);
  expect(refresh).not.toHaveBeenCalled();
});
