import { act, renderHook } from "@testing-library/react-native";

import type { Todo } from "@/lib/api";
import {
  nextReminderChange,
  useReminderClock,
} from "@/features/todos/hooks/useReminderClock";
import {
  firstOverdueHomeTodo,
  listHomeUrgentTodos,
} from "@/features/todos/model/homeUrgentTodos";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";
import { todosForView } from "@/features/todos/model/todoListFilter";

const foreground: ((state: string) => void)[] = [];
jest.mock("@/lib/foregroundRefresh", () => ({
  onAppStateChange: (listener: (state: string) => void) => {
    foreground.push(listener);
    return () => foreground.splice(foreground.indexOf(listener), 1);
  },
}));

const START = new Date("2026-10-24T12:00:00.000Z");

function todo(id: string, dueAt: string | null, checked = false, notifyAt?: string): Todo {
  // The server's notify_at: 10 minutes before it is due unless given.
  const notify = notifyAt ?? (dueAt ? new Date(Date.parse(dueAt) - 10 * 60_000).toISOString() : null);
  return { id, content: id, due_at: dueAt, checked, notify_at: notify } as Todo;
}

beforeEach(() => {
  jest.useFakeTimers({ now: START });
  foreground.length = 0;
});
afterEach(() => {
  jest.useRealTimers();
});

describe("nextReminderChange", () => {
  it("is the next notify_at or due time of an open reminder", () => {
    const todos = [
      todo("later", "2026-10-24T13:00:00.000Z"),
      todo("soon", "2026-10-24T12:30:00.000Z"),
      todo("done", "2026-10-24T12:05:00.000Z", true),
      todo("someday", null),
    ];
    // "soon"'s reminder goes out at 12:20.
    expect(nextReminderChange(todos, START)).toBe(
      Date.parse("2026-10-24T12:20:00.000Z"),
    );
    // Inside the window, its due time is next.
    const inWindow = new Date("2026-10-24T12:25:00.000Z");
    expect(nextReminderChange(todos, inWindow)).toBe(
      Date.parse("2026-10-24T12:30:00.000Z"),
    );
  });

  it("is the notify_at the server gave, not due - lead: quiet hours hold it until 07:00", () => {
    const todos = [todo("night", "2026-10-24T23:30:00.000Z", false, "2026-10-25T07:00:00.000Z")];
    const late = new Date("2026-10-24T23:00:00.000Z");
    // Its due time (23:30) comes first, then midnight; never 23:20.
    expect(nextReminderChange(todos, late)).toBe(Date.parse("2026-10-24T23:30:00.000Z"));
    const pastDue = new Date("2026-10-24T23:40:00.000Z");
    const midnight = new Date(pastDue.getFullYear(), pastDue.getMonth(), pastDue.getDate() + 1).getTime();
    expect(nextReminderChange(todos, pastDue)).toBe(Math.min(midnight, Date.parse("2026-10-25T07:00:00.000Z")));
  });

  it("is null when no open reminder has a due time", () => {
    const todos = [
      todo("done", "2026-10-25T09:00:00.000Z", true),
      todo("someday", null),
    ];
    expect(nextReminderChange(todos, START)).toBeNull();
  });

  it("is the next local midnight once every due time has passed", () => {
    const todos = [todo("past", "2026-10-24T11:00:00.000Z")];
    const midnight = new Date(START.getFullYear(), START.getMonth(), START.getDate() + 1);
    expect(nextReminderChange(todos, START)).toBe(midnight.getTime());
  });
});

describe("useReminderClock", () => {
  it("moves on when a reminder falls due, so Home shows it without a restart", async () => {
    // Saved in chat for 5 minutes from now: in the lead window, not yet overdue.
    const todos = [
      todo("Start anatomy study session", "2026-10-24T12:05:00.000Z"),
    ];
    const { result } = await renderHook(() => useReminderClock(todos));
    expect(
      firstOverdueHomeTodo(listHomeUrgentTodos(todos, result.current)),
    ).toBeUndefined();

    await act(async () => {
      jest.advanceTimersByTime(5 * 60_000 + 1_000);
    });

    expect(result.current.getTime()).toBeGreaterThan(
      Date.parse("2026-10-24T12:05:00.000Z"),
    );
    expect(
      firstOverdueHomeTodo(listHomeUrgentTodos(todos, result.current))?.id,
    ).toBe("Start anatomy study session");
  });

  it("reads the clock again when the app comes back to the foreground", async () => {
    const { result } = await renderHook(() => useReminderClock([]));
    const before = result.current.getTime();
    jest.setSystemTime(new Date("2026-10-24T15:00:00.000Z"));

    await act(async () => {
      foreground.forEach((listener) => listener("active"));
    });

    expect(result.current.getTime()).toBeGreaterThanOrEqual(
      Date.parse("2026-10-24T15:00:00.000Z"),
    );
    expect(result.current.getTime()).toBeGreaterThan(before);
  });

  it("reads the clock again when the list changes", async () => {
    const { result, rerender } = await renderHook(
      ({ todos }: { todos: Todo[] }) => useReminderClock(todos),
      { initialProps: { todos: [] as Todo[] } },
    );
    jest.setSystemTime(new Date("2026-10-24T14:00:00.000Z"));

    // A to-do saved already overdue is overdue at once.
    const saved = [todo("Call mom", "2026-10-24T13:30:00.000Z")];
    await act(async () => {
      await rerender({ todos: saved });
    });

    expect(
      firstOverdueHomeTodo(listHomeUrgentTodos(saved, result.current))?.id,
    ).toBe("Call mom");
  });

  it("moves on at local midnight, so the list regroups while the app stays open", async () => {
    // 23:59 local; due at 9:00 tomorrow, well past the lead window.
    jest.setSystemTime(new Date(2026, 9, 24, 23, 59, 0));
    const todos = [todo("Dentist", new Date(2026, 9, 25, 9, 0, 0).toISOString())];
    const { result } = await renderHook(() => useReminderClock(todos));
    const headings = () => buildTodoListRows(todos, result.current)
      .flatMap((row) => (row.kind === "heading" ? [row.section] : []));
    expect(headings()).toEqual(["tomorrow"]);

    await act(async () => {
      jest.advanceTimersByTime(2 * 60_000);
    });

    expect(headings()).toEqual(["today"]);
    expect(todosForView(todos, "today", result.current).map((item) => item.id)).toEqual(["Dentist"]);
  });
});
