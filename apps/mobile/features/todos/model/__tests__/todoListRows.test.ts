import type { Todo } from "@/lib/api";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";

function todo(id: string, dueAt: string | null, checked = false): Todo {
  return {
    id,
    content: id,
    topic: "General",
    checked,
    due_at: dueAt,
    recurrence_rule: null,
    sort_order: null,
    chat_id: null,
    created_at: `2026-09-0${id.length}T08:00:00.000Z`,
    updated_at: `2026-09-0${id.length}T09:00:00.000Z`,
    notify_at: null,
  };
}

it("groups dated and plain to-dos into a single urgency-ordered list", () => {
  const now = new Date(2026, 8, 22, 12, 0, 0);
  const rows = buildTodoListRows([
    todo("overdue", new Date(2026, 8, 21, 9).toISOString()),
    todo("today", new Date(2026, 8, 22, 17).toISOString()),
    todo("tomorrow", new Date(2026, 8, 23, 10).toISOString()),
    todo("future", new Date(2026, 8, 25, 10).toISOString()),
    todo("plain", null),
    todo("done", null, true),
  ], now);

  expect(rows.map((row) => (row.kind === "heading" ? row.section : row.todo.id))).toEqual([
    "overdue",
    "overdue",
    "today",
    "today",
    "tomorrow",
    "tomorrow",
    "date",
    "future",
    "anytime",
    "plain",
    "completed",
    "done",
  ]);
});

it("treats an invalid due date as an anytime to-do", () => {
  const rows = buildTodoListRows([todo("invalid", "not-a-date")], new Date(2026, 8, 22));
  expect(rows).toMatchObject([
    { kind: "heading", section: "anytime", count: 1 },
    { kind: "todo", todo: { id: "invalid" } },
  ]);
});

// A later day took each of its to-dos by copying the day so far, and every comparison
// parsed both due dates: 20,000 to-dos on one day took 1.5-1.8 s (jest). A time limit
// on the fix failed on a busy CI runner (907 ms, 2026-10-29), so these check the work.
const NOW = new Date(2026, 8, 22, 9);

function busyDay(count: number): Todo[] {
  return Array.from({ length: count }, (_, i) =>
    todo(`t${i}`, new Date(2026, 8, 25, 9, i % 600).toISOString()));
}

it("lists a very busy day in order", () => {
  const rows = buildTodoListRows(busyDay(20_000), NOW);
  expect(rows).toHaveLength(20_001);
  expect(rows[0]).toMatchObject({ kind: "heading", section: "date", count: 20_000 });
  expect(rows[1]).toMatchObject({ kind: "todo", todo: { due_at: new Date(2026, 8, 25, 9, 0).toISOString() } });
});

it("reads each due date a fixed number of times, not once per comparison", () => {
  let reads = 0;
  const busy = busyDay(5_000).map((item) => {
    const dueAt = item.due_at;
    return Object.defineProperty({ ...item }, "due_at", {
      get: () => {
        reads += 1;
        return dueAt;
      },
    });
  });
  buildTodoListRows(busy, NOW);
  // Two reads today; one per comparison would be ~18 per to-do.
  expect(reads).toBeLessThanOrEqual(4 * busy.length);
});

// The same 20,000 to-dos as ten days' worth of 2,000, timed in turn so a slow machine
// slows both: linear work costs about the same, a copy per to-do about 10x.
it("grows linearly with a busy day", () => {
  const small = busyDay(2_000);
  const large = busyDay(20_000);
  const timed = (run: () => void): number => {
    const start = performance.now();
    run();
    return performance.now() - start;
  };
  buildTodoListRows(large, NOW);
  let tenSmall = Number.POSITIVE_INFINITY;
  let oneLarge = Number.POSITIVE_INFINITY;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    tenSmall = Math.min(tenSmall, timed(() => {
      for (let day = 0; day < 10; day += 1) buildTodoListRows(small, NOW);
    }));
    oneLarge = Math.min(oneLarge, timed(() => buildTodoListRows(large, NOW)));
  }
  expect(oneLarge).toBeLessThan(4 * tenSmall);
});
