import type { Todo } from "@/lib/api";
import { localDateKey } from "@/features/todos/model/dateKey";

export type TodoView = "all" | "open" | "completed" | "today";

/** Narrow the list for the header menu. Today is open items due today or overdue. */
export function todosForView(todos: Todo[], view: TodoView, now = new Date()): Todo[] {
  if (view === "completed") return todos.filter((todo) => todo.checked);
  if (view === "open") return todos.filter((todo) => !todo.checked);
  if (view === "today") {
    const today = localDateKey(now);
    return todos.filter((todo) => {
      if (todo.checked || !todo.due_at) return false;
      const due = new Date(todo.due_at);
      return Number.isFinite(due.getTime()) && localDateKey(due) <= today;
    });
  }
  return todos;
}

/**
 * The view to show after adding a to-do due at `due`: this one when it lists the new item,
 * else "open". An undated or later to-do added on Today used to vanish from sight.
 */
export function viewForNewTodo(view: TodoView, due: Date | null, now = new Date()): TodoView {
  const added = { checked: false, due_at: due ? due.toISOString() : null } as Todo;
  return todosForView([added], view, now).length > 0 ? view : "open";
}

/** Open first, then the soonest due (undated last), then the newest. */
export function sortOpen(items: Todo[]): Todo[] {
  return [...items].sort((a, b) => {
    if (a.checked !== b.checked) return Number(a.checked) - Number(b.checked);
    const aDue = a.due_at ? new Date(a.due_at).getTime() : Number.POSITIVE_INFINITY;
    const bDue = b.due_at ? new Date(b.due_at).getTime() : Number.POSITIVE_INFINITY;
    if (aDue !== bDue) return aDue - bDue;
    return b.created_at.localeCompare(a.created_at);
  });
}
