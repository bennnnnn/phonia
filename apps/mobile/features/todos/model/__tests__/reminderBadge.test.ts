import type { Todo } from "@/lib/api";
import {
  countUnseenUrgentReminders,
  listUrgentReminders,
  reminderGoesOutAt,
} from "@/features/todos/model/reminderBadge";

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

const now = new Date("2026-06-27T12:00:00.000Z");

describe("reminderBadge: a reminder counts once the server's notify_at has come", () => {
  it("includes one whose notify_at has passed, before its due time", () => {
    const soon = todo({ id: "2", content: "Soon", due_at: "2026-06-27T12:10:00.000Z", notify_at: "2026-06-27T11:55:00.000Z" });
    expect(listUrgentReminders([soon], now)).toHaveLength(1);
  });

  it("excludes one whose notify_at is still to come, however close its due time", () => {
    const later = todo({ id: "3", content: "Evening", due_at: "2026-06-27T12:05:00.000Z", notify_at: "2026-06-27T12:01:00.000Z" });
    expect(listUrgentReminders([later], now)).toEqual([]);
  });

  it("waits out quiet hours with push: due 23:30, notify_at 07:00, nothing at 23:25 or 23:45", () => {
    const night = todo({ id: "n", content: "Night", due_at: "2026-06-27T23:30:00.000Z", notify_at: "2026-06-28T07:00:00.000Z" });
    // The lead window (due - 10) and the due time have both passed; the reminder has not gone out.
    expect(listUrgentReminders([night], new Date("2026-06-27T23:25:00.000Z"))).toEqual([]);
    expect(listUrgentReminders([night], new Date("2026-06-27T23:45:00.000Z"))).toEqual([]);
    expect(listUrgentReminders([night], new Date("2026-06-28T07:00:00.000Z"))).toEqual([night]);
  });

  it("keeps an overdue one the server gave no instant (48 hours past due)", () => {
    const late = todo({ id: "1", content: "Late", due_at: "2026-06-24T10:00:00.000Z" });
    expect(reminderGoesOutAt(late)).toBe(Date.parse("2026-06-24T10:00:00.000Z"));
    expect(listUrgentReminders([late], now).map((t) => t.id)).toEqual(["1"]);
  });

  it("excludes checked and undated items", () => {
    const done = todo({ id: "4", content: "Done", due_at: "2026-06-27T11:00:00.000Z", notify_at: "2026-06-27T10:50:00.000Z", checked: true });
    const undated = todo({ id: "5", content: "Milk" });
    expect(listUrgentReminders([done, undated], now)).toHaveLength(0);
    expect([reminderGoesOutAt(done), reminderGoesOutAt(undated)]).toEqual([null, null]);
  });

  it("counts only unseen urgent reminders", () => {
    const overdue = todo({ id: "1", content: "Late", due_at: "2026-06-27T10:00:00.000Z", notify_at: "2026-06-27T09:50:00.000Z" });
    const soon = todo({ id: "2", content: "Soon", due_at: "2026-06-27T12:10:00.000Z", notify_at: "2026-06-27T12:00:00.000Z" });
    const seen = new Set<string>(["1"]);
    expect(countUnseenUrgentReminders([overdue, soon], seen, now)).toBe(1);
  });
});
