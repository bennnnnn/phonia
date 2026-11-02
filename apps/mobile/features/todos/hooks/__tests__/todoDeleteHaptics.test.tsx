/**
 * Deleting a to-do feels like deleting a chat: nothing when the swipe's Delete opens the
 * confirm, one destructive haptic once the delete lands, none on cancel or failure.
 */
import React from "react";
import { Alert, View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { TodoRow } from "@/features/todos/components/TodoRow";
import { useTodosActions } from "@/features/todos/hooks/useTodosActions";
import { api, type Todo } from "@/lib/api";
import { notifyDestructive, notifySuccess, notifyWarning, selection, tap } from "@/lib/haptics";

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
  notifySuccess: jest.fn(),
  notifyWarning: jest.fn(),
  notifyDestructive: jest.fn(),
}));
jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const { View: MockView } = jest.requireActual<typeof import("react-native")>("react-native");
  /** The row and its swipe actions, both on screen. */
  function MockSwipeable({ children, renderRightActions }: {
    children: React.ReactNode;
    renderRightActions: () => React.ReactNode;
  }) {
    return (
      <MockView>
        {children}
        {renderRightActions()}
      </MockView>
    );
  }
  return MockSwipeable;
});
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/lib/i18n", () => ({ __esModule: true, default: { t: (key: string) => key }, ensureLocale: jest.fn() }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/features/todos/model/reminderSeen", () => ({ markReminderIdsSeen: jest.fn(async () => undefined) }));
jest.mock("@/features/todos/model/todoReminders", () => ({
  syncTodoReminders: jest.fn(), cancelTodoReminder: jest.fn(async () => undefined),
}));
jest.mock("@/lib/api", () => ({ api: { createTodo: jest.fn(), updateTodo: jest.fn(), deleteTodo: jest.fn() } }));

const A: Todo = { id: "a", content: "Tea", topic: "General", checked: false,
  due_at: null, sort_order: null, chat_id: null, created_at: "2026-09-04", updated_at: "2026-09-04", notify_at: null };
const B: Todo = { ...A, id: "b", content: "Books" };
let rows: Todo[];
let actions: ReturnType<typeof useTodosActions>;

function Probe() {
  const setTodos = (update: React.SetStateAction<Todo[]>) => {
    rows = typeof update === "function" ? update(rows) : update;
  };
  const result = useTodosActions({ token: "token", userId: "user", todos: rows, setTodos,
    refresh: async () => undefined, getTodos: () => rows, isCurrentView: () => true });
  React.useLayoutEffect(() => { actions = result; });
  return (
    <View>
      {rows.map((todo) => (
        <TodoRow key={todo.id} todo={todo} section="today" onToggle={jest.fn()} onDelete={result.handleDeleteItem} />
      ))}
    </View>
  );
}

const haptics = [tap, selection, notifySuccess, notifyWarning, notifyDestructive];
const hapticCount = () => haptics.reduce((sum, fn) => sum + jest.mocked(fn).mock.calls.length, 0);
/** The confirm dialog's Delete (no DialogHost in tests: it falls back to Alert.alert). */
const confirmDelete = () => jest.mocked(Alert.alert).mock.calls.at(-1)?.[2]?.[1]?.onPress as () => Promise<void>;
const cancelDelete = () => jest.mocked(Alert.alert).mock.calls.at(-1)?.[2]?.[0]?.onPress as () => void;

beforeEach(() => {
  jest.clearAllMocks();
  rows = [A, B];
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

it("asks before deleting without a haptic, then plays one destructive haptic once it is gone", async () => {
  jest.mocked(api.deleteTodo).mockResolvedValue(undefined as never);
  const view = await render(<Probe />);
  await act(async () => { fireEvent.press(view.getAllByLabelText("common.delete")[0]); });
  expect(Alert.alert).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(0);
  await act(async () => { await confirmDelete()(); });
  expect(api.deleteTodo).toHaveBeenCalledWith("token", "a");
  expect(notifyDestructive).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(1);
});

it("plays nothing when the delete is cancelled", async () => {
  const view = await render(<Probe />);
  await act(async () => { fireEvent.press(view.getAllByLabelText("common.delete")[0]); });
  await act(async () => { cancelDelete()?.(); });
  expect(api.deleteTodo).not.toHaveBeenCalled();
  expect(hapticCount()).toBe(0);
});

it("plays no destructive haptic for a delete that failed", async () => {
  jest.mocked(api.deleteTodo).mockRejectedValue(new Error("offline"));
  await render(<Probe />);
  actions.handleDeleteItem(A);
  await act(async () => { await confirmDelete()(); });
  expect(notifyDestructive).not.toHaveBeenCalled();
});

it("plays one destructive haptic for a bulk delete", async () => {
  jest.mocked(api.deleteTodo).mockResolvedValue(undefined as never);
  await render(<Probe />);
  await act(async () => { await actions.handleDeleteMany(["a", "b"]); });
  expect(api.deleteTodo).toHaveBeenCalledTimes(2);
  expect(notifyDestructive).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(1);
});
