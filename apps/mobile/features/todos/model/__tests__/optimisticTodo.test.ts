import {
  OPTIMISTIC_TODO_ID_PREFIX,
  buildOptimisticTodo,
  removeTodoById,
  replaceTodoById,
} from "@/features/todos/model/optimisticTodo";

describe("optimisticTodo", () => {
  it("builds a pending row with a local id prefix", () => {
    const row = buildOptimisticTodo({
      content: "Milk",
      topic: "Groceries",
      sortOrder: 2,
    });
    expect(row.id.startsWith(OPTIMISTIC_TODO_ID_PREFIX)).toBe(true);
    expect(row).toMatchObject({
      content: "Milk",
      topic: "Groceries",
      checked: false,
      due_at: null,
      sort_order: 2,
      chat_id: null,
    });
  });

  it("replaces and removes by id", () => {
    const first = buildOptimisticTodo({ content: "A", topic: "General" });
    const second = buildOptimisticTodo({ content: "B", topic: "General" });
    const swapped = { ...second, id: "server-1", content: "B done" };
    expect(replaceTodoById([first, second], second.id, swapped)).toEqual([
      first,
      swapped,
    ]);
    expect(removeTodoById([first, second], first.id)).toEqual([second]);
  });

  it("appends when the optimistic id was dropped by a concurrent refresh", () => {
    const server = {
      ...buildOptimisticTodo({ content: "Milk", topic: "Groceries" }),
      id: "server-1",
    };
    const leftover = buildOptimisticTodo({ content: "Eggs", topic: "Groceries" });
    expect(replaceTodoById([leftover], "local-todo-missing", server)).toEqual([
      leftover,
      server,
    ]);
  });
});
