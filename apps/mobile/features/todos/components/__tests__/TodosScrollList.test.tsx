import { render } from "@testing-library/react-native";

import { TodosScrollList } from "@/features/todos/components/TodosScrollList";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";
import type { Todo } from "@/lib/api";

type Cell = { kind: string; todos?: Todo[] };
const mockCells: Cell[][] = [];

// The shared stand-in, which draws every cell, keeping the cells it was given.
jest.mock("@shopify/flash-list", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    FlashList: ({ data, renderItem, keyExtractor }: {
      data: Cell[];
      renderItem: (info: { item: Cell; index: number }) => React.ReactNode;
      keyExtractor: (item: Cell) => string;
    }) => {
      mockCells.push(data);
      return React.createElement(React.Fragment, null, ...data.map((item, index) =>
        React.createElement(React.Fragment, { key: keyExtractor(item) }, renderItem({ item, index }))));
    },
  };
});
jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const { View } = jest.requireActual("react-native");
  return { __esModule: true, default: View };
});

const NOW = new Date(2026, 9, 25, 8);

function todo(id: string, due: Date | null, content = id): Todo {
  return {
    id, content, topic: "General", checked: false, due_at: due?.toISOString() ?? null, recurrence_rule: null,
    sort_order: null, chat_id: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
  } as Todo;
}

function list(todos: Todo[]) {
  const noop = jest.fn();
  return render(
    <TodosScrollList rows={buildTodoListRows(todos, NOW)} now={NOW} showEmpty={false} error={false} listHeader={<></>}
      busyTodoIds={new Set()} onToggle={noop} onOpen={noop} onDeleteItem={noop} />,
  );
}

beforeEach(() => { mockCells.length = 0; });

it("draws each day's heading over its cards, same-time to-dos together with their clash", async () => {
  const ui = await list([
    todo("call", new Date(2026, 9, 25, 15), "Call Sam"),
    todo("pay", new Date(2026, 9, 25, 15, 5), "Pay rent"),
    todo("gym", new Date(2026, 9, 25, 18), "Gym"),
    todo("milk", null, "Buy milk"),
  ]);
  for (const text of ["todos.group_today", "Call Sam", "Pay rent", "Gym", "todos.group_anytime", "Buy milk", "todos.day_clash_pair"]) {
    expect(ui.getByText(text)).toBeTruthy();
  }
  expect(mockCells.at(-1)!.map((cell) => cell.kind === "card" ? cell.todos!.map((t) => t.id).join("+") : cell.kind))
    .toEqual(["heading", "call+pay", "gym", "heading", "milk"]);
});

// A day was one cell holding every card: 300 to-dos shown mounted 300 rows (jest,
// FlashList's 400x900 layout stand-in), now about 30, the ones on screen.
it("gives FlashList one cell per card, so a long list mounts only the cards on screen", async () => {
  const todos = Array.from({ length: 300 }, (_, i) => todo(`t${i}`, new Date(2026, 9, 25, 9, i * 20)));
  await list(todos);
  const cards = mockCells.at(-1)!.filter((cell) => cell.kind === "card");
  expect(cards).toHaveLength(300);
  expect(cards.every((cell) => cell.todos?.length === 1)).toBe(true);
});

// Each row and heading wrote its date with toLocale*String, an ICU formatter per call:
// 318 for these 300 to-dos (about 40 µs each in Node), and 18 more per re-render.
// lib/datetime/format.ts keeps one formatter per language, zone, clock and style.
it("builds a handful of date formatters for a long list, and none to draw it again", async () => {
  const todos = Array.from({ length: 300 }, (_, i) => todo(`t${i}`, new Date(2026, 9, 20 + (i % 10), 9, i)));
  const dateText = jest.spyOn(Date.prototype, "toLocaleDateString");
  const timeText = jest.spyOn(Date.prototype, "toLocaleTimeString");
  const built = jest.spyOn(Intl, "DateTimeFormat");
  try {
    const builds = () => built.mock.calls.length + dateText.mock.calls.length + timeText.mock.calls.length;
    const ui = await list(todos);
    expect(builds()).toBeLessThanOrEqual(3);
    built.mockClear();
    await ui.rerender(
      <TodosScrollList rows={buildTodoListRows(todos, NOW)} now={NOW} showEmpty={false} error={false}
        listHeader={<></>} busyTodoIds={new Set()} onToggle={jest.fn()} onOpen={jest.fn()} onDeleteItem={jest.fn()} />,
    );
    expect(built).not.toHaveBeenCalled();
    expect(dateText).not.toHaveBeenCalled();
    expect(timeText).not.toHaveBeenCalled();
  } finally {
    jest.restoreAllMocks();
  }
});
