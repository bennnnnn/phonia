/**
 * A row's time turns to the overdue color when the to-do clock passes it, while the
 * list stays open. The rows are memoized, so the color comes from the clock the list
 * is drawn with, never from the time of the row's last render. A screen reader hears
 * "overdue" whenever the row shows it.
 */
import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { render } from "@testing-library/react-native";

import { TodosScrollList } from "@/features/todos/components/TodosScrollList";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";
import type { Todo } from "@/lib/api";
import { formatDate } from "@/lib/datetime/format";

jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const { View: MockView } = jest.requireActual<typeof import("react-native")>("react-native");
  return function MockSwipeable({ children }: { children: ReactNode }) {
    return <MockView>{children}</MockView>;
  };
});
jest.mock("@/lib/haptics", () => ({ selection: jest.fn() }));
// Each color is its token's name.
jest.mock("@/lib/theme", () => ({ useTheme: () => new Proxy({}, { get: (_target, key) => String(key) }) }));

const TODO = {
  id: "call", content: "Call the bank", topic: "General", checked: false,
  due_at: "2026-10-24T12:01:00.000Z", sort_order: null, chat_id: null,
  created_at: "2026-10-24T08:00:00.000Z", updated_at: "2026-10-24T08:00:00.000Z",
} as Todo;
const noop = () => {};
const BUSY = new Set<string>();

function list(now: Date, todos = [TODO]) {
  return (
    <TodosScrollList
      rows={buildTodoListRows(todos, now)}
      now={now}
      showEmpty={false}
      error={false}
      listHeader={<View />}
      busyTodoIds={BUSY}
      onToggle={noop}
      onOpen={noop}
      onDeleteItem={noop}
    />
  );
}

afterEach(() => {
  jest.useRealTimers();
});

it("shows a time that falls due while the list is open as overdue", async () => {
  jest.useFakeTimers({ now: new Date("2026-10-24T12:00:00.000Z") });
  const ui = await render(list(new Date()));
  const timeColor = () => StyleSheet.flatten(ui.getByText(/\d:\d\d/).props.style).color;
  expect(timeColor()).not.toBe("danger");

  // The to-do clock wakes just after the due time and the list is drawn again.
  jest.setSystemTime(new Date("2026-10-24T12:01:00.500Z"));
  await ui.rerender(list(new Date()));

  expect(timeColor()).toBe("danger");
});

it("says overdue to a screen reader when the row shows it, and only then", async () => {
  jest.useFakeTimers({ now: new Date("2026-10-24T12:00:00.000Z") });
  // Done before its time: the row shows no time and no overdue mark.
  const done = { ...TODO, id: "paid", content: "Pay rent", checked: true, due_at: "2026-10-24T09:00:00.000Z" };
  const time = formatDate(new Date(TODO.due_at!), "time");
  const ui = await render(list(new Date(), [TODO, done]));
  expect(ui.getByLabelText(`Call the bank, ${time}`)).toBeTruthy();

  jest.setSystemTime(new Date("2026-10-24T12:01:00.500Z"));
  await ui.rerender(list(new Date(), [TODO, done]));

  expect(ui.getByLabelText(`Call the bank, ${time}, todos.row_overdue`)).toBeTruthy();
  expect(ui.queryByLabelText(`Call the bank, ${time}`)).toBeNull();
  expect(ui.getByRole("button", { name: "Pay rent" })).toBeTruthy();
});
