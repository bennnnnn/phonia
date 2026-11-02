import { todosForView, viewForNewTodo } from "@/features/todos/model/todoListFilter";
import type { Todo } from "@/lib/api";

function todo(partial: Partial<Todo> & Pick<Todo, "id">): Todo {
  return {
    content: partial.id,
    topic: "General",
    checked: false,
    due_at: null,
    sort_order: null,
    chat_id: null,
    created_at: "2026-09-01T00:00:00.000Z",
    updated_at: "2026-09-01T00:00:00.000Z",
    notify_at: null,
    ...partial,
  };
}

const now = new Date(2026, 8, 25, 12, 0, 0);

describe("todosForView", () => {
  const rows = [
    todo({ id: "open", due_at: "2026-09-26T16:00:00.000Z" }),
    todo({ id: "today", due_at: new Date(2026, 8, 25, 15, 0, 0).toISOString() }),
    todo({ id: "done", checked: true, due_at: new Date(2026, 8, 25, 9, 0, 0).toISOString() }),
    todo({ id: "anytime" }),
  ];

  it("keeps every to-do on all", () => {
    expect(todosForView(rows, "all", now).map((item) => item.id)).toEqual([
      "open",
      "today",
      "done",
      "anytime",
    ]);
  });

  it("splits open and completed", () => {
    expect(todosForView(rows, "open", now).map((item) => item.id)).toEqual([
      "open",
      "today",
      "anytime",
    ]);
    expect(todosForView(rows, "completed", now).map((item) => item.id)).toEqual(["done"]);
  });

  it("previews open to-dos that are overdue or due today", () => {
    const withOverdue = [
      ...rows,
      todo({ id: "overdue", due_at: new Date(2026, 8, 24, 15, 0, 0).toISOString() }),
      todo({ id: "later", due_at: new Date(2026, 8, 30, 15, 0, 0).toISOString() }),
    ];
    expect(todosForView(withOverdue, "today", now).map((item) => item.id)).toEqual([
      "today",
      "overdue",
    ]);
  });
});

describe("viewForNewTodo", () => {
  it("keeps the view when it lists the new to-do", () => {
    expect(viewForNewTodo("today", new Date(2026, 8, 25, 18, 0, 0), now)).toBe("today");
    expect(viewForNewTodo("all", null, now)).toBe("all");
    expect(viewForNewTodo("open", new Date(2026, 9, 3), now)).toBe("open");
  });

  it("shows open to-dos when the view would hide it", () => {
    expect(viewForNewTodo("today", null, now)).toBe("open");
    expect(viewForNewTodo("today", new Date(2026, 8, 28), now)).toBe("open");
    expect(viewForNewTodo("completed", null, now)).toBe("open");
  });
});
