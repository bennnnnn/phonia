import type { RecurrenceRule, Todo } from "@/lib/api";

export const OPTIMISTIC_TODO_ID_PREFIX = "local-todo-";

let optimisticTodoSeq = 0;

function newOptimisticTodoId(): string {
  optimisticTodoSeq += 1;
  return `${OPTIMISTIC_TODO_ID_PREFIX}${Date.now()}-${optimisticTodoSeq}`;
}

export function buildOptimisticTodo(fields: {
  content: string;
  topic: string;
  dueAt?: string | null;
  recurrenceRule?: RecurrenceRule | null;
  sortOrder?: number | null;
}): Todo {
  const now = new Date().toISOString();
  return {
    id: newOptimisticTodoId(),
    content: fields.content,
    topic: fields.topic,
    checked: false,
    due_at: fields.dueAt ?? null,
    recurrence_rule: fields.recurrenceRule ?? null,
    sort_order: fields.sortOrder ?? null,
    chat_id: null,
    created_at: now,
    updated_at: now,
    // The server works out when its reminder goes out; none until it has saved it.
    notify_at: null,
  };
}

export function replaceTodoById(todos: Todo[], id: string, next: Todo): Todo[] {
  let found = false;
  const mapped = todos.flatMap((item) => {
    if (item.id === id || item.id === next.id) {
      if (found) return [];
      found = true;
      return [next];
    }
    return [item];
  });
  return found ? mapped : [...todos, next];
}

export function removeTodoById(todos: Todo[], id: string): Todo[] {
  return todos.filter((item) => item.id !== id);
}
