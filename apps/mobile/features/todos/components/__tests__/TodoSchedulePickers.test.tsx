import { act, fireEvent, render } from "@testing-library/react-native";

import { TodoEditorSheet } from "@/features/todos/components/TodoEditorSheet";
import type { Todo } from "@/lib/api";

type TimeOfDay = { hour: number; minute: number };
type DateDialog = { visible: boolean; value: Date; onConfirm: (date: Date) => void; onCancel: () => void };
type TimeDialog = { visible: boolean; value: TimeOfDay; onConfirm: (time: TimeOfDay) => void; onCancel: () => void };
let mockDate: DateDialog;
let mockTime: TimeDialog;
let mockForm: { onSave: () => void };
jest.mock("@/ui/pickers/DatePickerDialog", () => ({
  DatePickerDialog: (props: DateDialog) => { mockDate = props; return null; },
}));
jest.mock("@/ui/pickers/TimePickerDialog", () => ({
  TimePickerDialog: (props: TimeDialog) => { mockTime = props; return null; },
}));
jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
  ensureLocale: jest.fn(),
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({}) }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));
jest.mock("@/lib/haptics", () => ({ selection: jest.fn(), tap: jest.fn() }));
// The detail page asks the server for Remind at; signed out here, it asks nothing.
jest.mock("@/contexts/AuthContext", () => ({ useAuthOptional: () => null }));
jest.mock("@/lib/api", () => ({ api: { previewReminder: jest.fn() } }));
jest.mock("@/features/todos/model/todoReminders", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
}));
jest.mock("@/ui/overlay/Sheet", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Sheet: ({ visible, children }: { visible: boolean; children: React.ReactNode }) =>
      (visible ? <View>{children}</View> : null),
  };
});
jest.mock("@/ui/overlay/SheetFormHeader", () => ({
  SheetFormHeader: (props: typeof mockForm) => { mockForm = props; return null; },
}));

const original = new Date(2026, 8, 4, 9, 30);
const todo = { id: "todo-a", content: "Call Mom", due_at: original.toISOString(), checked: false } as Todo;
function editProps(save = jest.fn(), extra: Record<string, unknown> = {}) {
  return { visible: true, saving: false, todos: [todo], editTodo: todo, onClose: jest.fn(), onSave: save, ...extra };
}
beforeEach(() => jest.clearAllMocks());

it("creates a reminder from the date dialog and the clock", async () => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet visible saving={false} todos={[]} onClose={jest.fn()} onSave={save} />);
  await fireEvent.changeText(ui.getByPlaceholderText("todos.todo_placeholder"), "Call Mom");
  expect(mockDate.visible).toBe(false);
  await fireEvent.press(ui.getByLabelText("todos.add_date"));
  expect(mockDate.visible).toBe(true);
  await act(() => { mockDate.onConfirm(new Date(2026, 9, 12, 9, 30)); });
  expect(mockDate.visible).toBe(false);
  await fireEvent.press(ui.getByLabelText("todos.time_label"));
  expect(mockTime.visible).toBe(true);
  await act(() => { mockTime.onConfirm({ hour: 17, minute: 45 }); });
  expect(mockTime.visible).toBe(false);
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", new Date(2026, 9, 12, 17, 45), null, "General");
});

it("creates a plain to-do without opening the date picker", async () => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet visible saving={false} todos={[]} onClose={jest.fn()} onSave={save} />);
  await fireEvent.changeText(ui.getByPlaceholderText("todos.todo_placeholder"), "Buy milk");
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Buy milk", null, null, "General");
});

it("removes a date and its repeat rule together", async () => {
  const save = jest.fn();
  const repeating = { ...todo, recurrence_rule: "weekly" as const };
  const ui = await render(<TodoEditorSheet {...editProps(save)} editTodo={repeating} />);
  await fireEvent.press(ui.getByLabelText("todos.remove_date"));
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", null, null, "General");
});

it("edits the day and the time separately, keeping the other part", async () => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet {...editProps(save)} />);
  await fireEvent.press(ui.getByLabelText("todos.change_due"));
  expect(mockDate.value).toEqual(original);
  await act(() => { mockDate.onConfirm(new Date(2026, 10, 2, 0, 0)); });
  await fireEvent.press(ui.getByLabelText("todos.time_label"));
  expect(mockTime.value).toEqual({ hour: 9, minute: 30 });
  await act(() => { mockTime.onConfirm({ hour: 14, minute: 15 }); });
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledTimes(1);
  expect(save).toHaveBeenCalledWith("Call Mom", new Date(2026, 10, 2, 14, 15), null, "General");
});

it.each(["date", "time"] as const)("cancels a %s selection without changing the due date", async (step) => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet {...editProps(save)} />);
  await fireEvent.press(ui.getByLabelText(step === "date" ? "todos.change_due" : "todos.time_label"));
  const dialog = step === "date" ? mockDate : mockTime;
  expect(dialog.visible).toBe(true);
  await act(() => { dialog.onCancel(); });
  expect((step === "date" ? mockDate : mockTime).visible).toBe(false);
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", original, null, "General");
});

it("ignores a picker answer after unmount", async () => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet {...editProps(save)} />);
  await fireEvent.press(ui.getByLabelText("todos.change_due"));
  const answer = mockDate.onConfirm;
  await ui.unmount();
  await act(() => { answer(new Date(2027, 0, 1)); });
  expect(save).not.toHaveBeenCalled();
});

it("drops an earlier to-do's picker answer after changing targets", async () => {
  const save = jest.fn();
  const props = editProps(save);
  const ui = await render(<TodoEditorSheet {...props} />);
  await fireEvent.press(ui.getByLabelText("todos.change_due"));
  const stale = mockDate.onConfirm;
  const other = { ...todo, id: "todo-b" } as Todo;
  await ui.rerender(<TodoEditorSheet {...props} editTodo={other} />);
  await fireEvent.press(ui.getByLabelText("todos.change_due"));
  await act(() => { stale(new Date(2027, 0, 1)); });
  expect(mockDate.visible).toBe(true);
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", original, null, "General");
});

it("closes but keeps the date when OK arrives while saving", async () => {
  const save = jest.fn();
  const props = editProps(save);
  const ui = await render(<TodoEditorSheet {...props} />);
  await fireEvent.press(ui.getByLabelText("todos.change_due"));
  await ui.rerender(<TodoEditorSheet {...props} saving />);
  await act(() => { mockDate.onConfirm(new Date(2027, 0, 1)); });
  expect(mockDate.visible).toBe(false);
  await ui.rerender(<TodoEditorSheet {...props} />);
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", original, null, "General");
});

it("saves a repeat change from the edit sheet", async () => {
  const save = jest.fn();
  const ui = await render(<TodoEditorSheet {...editProps(save)} />);
  await fireEvent.press(ui.getByLabelText("todos.repeat_label, todos.repeat_none"));
  await fireEvent.press(ui.getByLabelText("todos.repeat_weekly"));
  await act(() => { mockForm.onSave(); });
  expect(save).toHaveBeenCalledWith("Call Mom", original, "weekly", "General");
});
