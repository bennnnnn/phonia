import type { HomeUrgentTodo, Todo } from "@/lib/api";
import { listUrgentReminders } from "@/features/todos/model/reminderBadge";

/**
 * Open reminders that have gone out (their `notify_at` has come, the badge's rule), the
 * five due soonest. Home shows the first overdue one.
 */
export function listHomeUrgentTodos(todos: Todo[], now = new Date()): HomeUrgentTodo[] {
  return listUrgentReminders(todos, now)
    .sort((a, b) => Date.parse(a.due_at!) - Date.parse(b.due_at!))
    .slice(0, 5)
    .map((todo) => ({
      id: todo.id,
      content: todo.content,
      topic: todo.topic,
      due_at: todo.due_at!,
      minutes_until: Math.floor((Date.parse(todo.due_at!) - now.getTime()) / 60_000),
    }));
}

export function firstOverdueHomeTodo(
  urgent: HomeUrgentTodo[],
): HomeUrgentTodo | undefined {
  return urgent.find((item) => item.minutes_until < 0);
}
