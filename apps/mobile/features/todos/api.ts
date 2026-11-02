import { request, requestRevalidated } from "@/lib/api/client";
import type { Page, RecurrenceRule, Todo } from "@/lib/api/types";

const TODO_PAGE_SIZE = 1000;
/** Completed to-dos older than this stay on the server until asked for. */
const RECENT_COMPLETED_DAYS = 30;

type TodoPage = Page<Todo> & { older_completed?: boolean };

/** The list, and whether older completed to-dos were left out of it. */
export type TodoList = { todos: Todo[]; olderCompleted: boolean };

/** The rows a confirmed reminder card wrote; `todos` is null when another tap saved it first. */
type ReminderProposalSaved = { items: unknown[]; todos: Todo[] | null; deleted_ids: string[] };

/**
 * Open to-dos and those completed in the last 30 days, or every row with
 * `allCompleted`. The whole list, completed rows of years ago included, was
 * downloaded on every visit (code-health audit NET-16); each page is now also
 * revalidated by its ETag, so an unchanged list costs a 304.
 */
async function listTodos(
  token: string,
  options?: { signal?: AbortSignal; allCompleted?: boolean },
): Promise<TodoList> {
  const rows = new Map<string, Todo>();
  const visitedCursors = new Set<string>();
  const window = options?.allCompleted ? "" : `&completed_days=${RECENT_COMPLETED_DAYS}`;
  let cursor: string | null = null;
  let olderCompleted = false;
  for (;;) {
    const suffix: string = cursor === null ? "" : `&cursor=${encodeURIComponent(cursor)}`;
    const page: TodoPage = await requestRevalidated<TodoPage>(
      `/todos/page?limit=${TODO_PAGE_SIZE}${window}${suffix}`,
      token,
      { signal: options?.signal },
    );
    if (cursor === null) olderCompleted = page.older_completed === true;
    page.items.forEach((row) => rows.set(row.id, row));
    if (page.next_cursor === null) return { todos: [...rows.values()], olderCompleted };
    if (visitedCursors.has(page.next_cursor)) throw new Error("Todo pagination did not advance");
    visitedCursors.add(page.next_cursor);
    cursor = page.next_cursor;
  }
}

export const todosApi = {
  listTodos,
  createTodo: (
    token: string,
    content: string,
    topic = "General",
    options?: {
      chatId?: string;
      dueAt?: string | null;
      recurrenceRule?: Todo["recurrence_rule"];
    },
  ) =>
    request<Todo>("/todos", token, {
      method: "POST",
      body: JSON.stringify({
        content,
        topic,
        chat_id: options?.chatId ?? null,
        due_at: options?.dueAt ?? undefined,
        recurrence_rule: options?.recurrenceRule ?? undefined,
      }),
    }),
  updateTodo: (
    token: string,
    id: string,
    patch: Partial<
      Pick<
        Todo,
        | "content"
        | "topic"
        | "checked"
        | "due_at"
        | "recurrence_rule"
        | "sort_order"
      >
    >,
  ) =>
    request<Todo>(`/todos/${id}`, token, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteTodo: (token: string, id: string) =>
    request<void>(`/todos/${id}`, token, { method: "DELETE" }),
  /**
   * The notify_at a to-do due at `dueAt` would get if it were saved now: the editor's
   * "Remind at" for a due time it has not saved. The server's lead time and quiet hours.
   */
  previewReminder: (
    token: string,
    dueAt: string,
    recurrenceRule: RecurrenceRule | null,
    signal?: AbortSignal,
  ) =>
    request<{ notify_at: string | null }>(
      `/todos/reminder-preview?due_at=${encodeURIComponent(dueAt)}${
        recurrenceRule ? `&recurrence_rule=${recurrenceRule}` : ""}`,
      token,
      { signal },
    ),
  /** Save the reminder change a chat card offered. A second tap is a no-op. */
  confirmReminderProposal: (token: string, proposalId: string) =>
    request<ReminderProposalSaved>(
      `/todos/proposals/${encodeURIComponent(proposalId)}/confirm`,
      token,
      { method: "POST" },
    ),
};
