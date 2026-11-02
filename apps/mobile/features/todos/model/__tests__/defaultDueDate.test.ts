import type { Todo } from "@/lib/api";
import { defaultDueDate } from "@/features/todos/model/dueDate";
import { sortOpen } from "@/features/todos/model/todoListFilter";

function todo(id: string, fields: Partial<Todo> = {}): Todo {
  return {
    id,
    content: id,
    topic: "General",
    checked: false,
    due_at: null,
    created_at: "2026-10-01T00:00:00Z",
    ...fields,
  } as Todo;
}

describe("sortOpen", () => {
  it("puts open before done, then the soonest due, undated last, then the newest", () => {
    const rows = [
      todo("done", { checked: true, due_at: "2026-10-02T09:00:00Z" }),
      todo("undated-old", { created_at: "2026-09-01T00:00:00Z" }),
      todo("later", { due_at: "2026-10-05T09:00:00Z" }),
      todo("undated-new", { created_at: "2026-10-03T00:00:00Z" }),
      todo("sooner", { due_at: "2026-10-03T09:00:00Z" }),
    ];
    expect(sortOpen(rows).map((row) => row.id)).toEqual([
      "sooner",
      "later",
      "undated-new",
      "undated-old",
      "done",
    ]);
  });

  it("leaves the input in its order", () => {
    const rows = [todo("b", { due_at: "2026-10-05T09:00:00Z" }), todo("a", { due_at: "2026-10-03T09:00:00Z" })];
    sortOpen(rows);
    expect(rows.map((row) => row.id)).toEqual(["b", "a"]);
  });
});

describe("defaultDueDate", () => {
  afterEach(() => jest.useRealTimers());

  it("is 9:00 today before nine in the morning", () => {
    jest.useFakeTimers({ now: new Date(2026, 9, 19, 7, 30) });
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 19, 9, 0, 0, 0));
  });

  it("is the next whole hour from nine on", () => {
    jest.useFakeTimers({ now: new Date(2026, 9, 19, 9, 0) });
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 19, 10, 0, 0, 0));
    jest.setSystemTime(new Date(2026, 9, 19, 23, 40));
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 20, 0, 0, 0, 0));
  });
});
