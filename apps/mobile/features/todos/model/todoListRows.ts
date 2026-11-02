import type { Todo } from "@/lib/api";
import { localDateKey } from "@/features/todos/model/dateKey";

export type TodoSection =
  | "overdue"
  | "today"
  | "tomorrow"
  | "date"
  | "anytime"
  | "completed";

export type TodoListRow =
  | { kind: "heading"; section: TodoSection; key: string; dayKey?: string; count: number }
  | { kind: "todo"; todo: Todo };

export function todoListRowKey(row: TodoListRow): string {
  if (row.kind === "todo") return `todo-${row.todo.id}`;
  return `heading-${row.key}`;
}

/** Soonest due first, then the newest. `due` holds each dated to-do's time, read once, not per comparison. */
function byDueThenCreated(due: Map<Todo, number>): (a: Todo, b: Todo) => number {
  return (a, b) => {
    const aDue = due.get(a) ?? Number.POSITIVE_INFINITY;
    const bDue = due.get(b) ?? Number.POSITIVE_INFINITY;
    if (aDue !== bDue) return aDue - bDue;
    return b.created_at.localeCompare(a.created_at);
  };
}

function appendGroup(
  rows: TodoListRow[],
  section: TodoSection,
  key: string,
  items: Todo[],
  dayKey?: string,
): void {
  if (!items.length) return;
  rows.push({ kind: "heading", section, key, dayKey, count: items.length });
  rows.push(...items.map((todo) => ({ kind: "todo" as const, todo })));
}

/** Build one urgency-ordered list, separated into readable day groups. */
export function buildTodoListRows(todos: Todo[], now = new Date()): TodoListRow[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const todayKey = localDateKey(today);
  const tomorrowKey = localDateKey(tomorrow);
  const overdue: Todo[] = [];
  const todayItems: Todo[] = [];
  const tomorrowItems: Todo[] = [];
  const anytime: Todo[] = [];
  const completed: Todo[] = [];
  const futureByDay = new Map<string, Todo[]>();
  const due = new Map<Todo, number>();

  for (const todo of todos) {
    if (todo.checked) {
      completed.push(todo);
      continue;
    }
    if (!todo.due_at) {
      anytime.push(todo);
      continue;
    }
    const at = new Date(todo.due_at);
    if (!Number.isFinite(at.getTime())) {
      anytime.push(todo);
      continue;
    }
    due.set(todo, at.getTime());
    const dayKey = localDateKey(at);
    if (dayKey < todayKey) overdue.push(todo);
    else if (dayKey === todayKey) todayItems.push(todo);
    else if (dayKey === tomorrowKey) tomorrowItems.push(todo);
    else {
      // Appended in place: copying the day on each to-do made a busy day quadratic.
      const day = futureByDay.get(dayKey);
      if (day) day.push(todo);
      else futureByDay.set(dayKey, [todo]);
    }
  }
  const sortByDueThenCreated = byDueThenCreated(due);

  const rows: TodoListRow[] = [];
  appendGroup(rows, "overdue", "overdue", overdue.sort(sortByDueThenCreated));
  appendGroup(rows, "today", todayKey, todayItems.sort(sortByDueThenCreated), todayKey);
  appendGroup(
    rows,
    "tomorrow",
    tomorrowKey,
    tomorrowItems.sort(sortByDueThenCreated),
    tomorrowKey,
  );
  for (const [dayKey, items] of [...futureByDay].sort(([a], [b]) => a.localeCompare(b))) {
    appendGroup(rows, "date", dayKey, items.sort(sortByDueThenCreated), dayKey);
  }
  appendGroup(
    rows,
    "anytime",
    "anytime",
    anytime.sort((a, b) => b.created_at.localeCompare(a.created_at)),
  );
  appendGroup(
    rows,
    "completed",
    "completed",
    completed.sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
  );
  return rows;
}
