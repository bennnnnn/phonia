import type { Todo } from "@/lib/api";
import {
  firstOverdueHomeTodo,
  listHomeUrgentTodos,
} from "@/features/todos/model/homeUrgentTodos";

function todo(partial: Partial<Todo> & Pick<Todo, "id" | "content">): Todo {
  return {
    topic: "General",
    checked: false,
    due_at: null,
    sort_order: null,
    chat_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    notify_at: null,
    ...partial,
  };
}

/** A to-do whose reminder went out `lead` minutes before it was due. */
function dated(id: string, dueAt: string, lead = 10): Todo {
  return todo({
    id,
    content: id,
    due_at: dueAt,
    notify_at: new Date(Date.parse(dueAt) - lead * 60_000).toISOString(),
  });
}

describe("listHomeUrgentTodos", () => {
  const now = new Date("2026-06-27T12:00:00.000Z");

  it("includes overdue reminders", () => {
    const urgent = listHomeUrgentTodos([dated("Pay rent", "2026-06-26T12:00:00.000Z")], now);
    expect(urgent.map((item) => item.id)).toEqual(["Pay rent"]);
    expect(urgent[0].minutes_until).toBeLessThan(0);
  });

  it("returns the first overdue reminder and ignores one whose reminder went out but is not due", () => {
    const overdue = dated("Late", "2026-06-26T12:00:00.000Z");
    const dueSoon = dated("Soon", "2026-06-27T12:05:00.000Z");
    expect(firstOverdueHomeTodo(listHomeUrgentTodos([overdue, dueSoon], now))?.id).toBe("Late");
    expect(listHomeUrgentTodos([dueSoon], now).map((item) => item.id)).toEqual(["Soon"]);
    expect(firstOverdueHomeTodo(listHomeUrgentTodos([dueSoon], now))).toBeUndefined();
  });

  it("shows an overdue reminder at its notify_at: quiet hours 22:00-07:00, due 23:30, from 07:00", () => {
    const night = todo({
      id: "night", content: "Call Sam", due_at: "2026-06-27T23:30:00.000Z", notify_at: "2026-06-28T07:00:00.000Z",
    });
    expect(firstOverdueHomeTodo(listHomeUrgentTodos([night], new Date("2026-06-27T23:45:00.000Z")))).toBeUndefined();
    expect(firstOverdueHomeTodo(listHomeUrgentTodos([night], new Date("2026-06-28T07:00:00.000Z")))?.id).toBe("night");
  });

  it("leaves out a reminder that has not gone out yet", () => {
    const later = dated("Later", "2026-06-27T14:00:00.000Z");
    expect(listHomeUrgentTodos([later], now)).toEqual([]);
  });

  it("excludes checked items and list items without due dates", () => {
    const done = { ...dated("Done", "2026-06-27T11:00:00.000Z"), checked: true };
    const listItem = todo({ id: "2", content: "Milk" });
    expect(listHomeUrgentTodos([done, listItem], now)).toEqual([]);
  });

  it("limits to five, due soonest first", () => {
    const items = Array.from({ length: 7 }, (_, index) =>
      dated(`Task ${index}`, new Date(now.getTime() - (index + 1) * 60_000).toISOString()));
    const urgent = listHomeUrgentTodos(items, now);
    expect(urgent.map((item) => item.id)).toEqual(["Task 6", "Task 5", "Task 4", "Task 3", "Task 2"]);
  });
});
