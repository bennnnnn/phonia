import {
  isRemotePushTrigger,
  shouldSyncLocalTodoReminders,
  todoIdFromNotificationData,
} from "@/features/todos/model/todoReminderPush";

describe("todo reminder push helpers", () => {
  it("reads todo_id from remote todo reminder payloads", () => {
    expect(
      todoIdFromNotificationData({ type: "todo_reminder", todo_id: "abc" }),
    ).toBe("abc");
    expect(todoIdFromNotificationData({ type: "todo_due", todo_id: "abc" })).toBe("abc");
    expect(todoIdFromNotificationData({ type: "email_suggestion", todo_id: "abc" })).toBe(
      null,
    );
    expect(todoIdFromNotificationData({ type: "todo_reminder" })).toBe(null);
  });

  it("treats only push triggers as remote", () => {
    expect(isRemotePushTrigger({ type: "push" })).toBe(true);
    expect(isRemotePushTrigger({ type: "date", date: new Date() })).toBe(false);
    expect(isRemotePushTrigger(null)).toBe(false);
  });
});

describe("shouldSyncLocalTodoReminders", () => {
  it("skips on-device scheduling only when the server holds this device's token", () => {
    expect(shouldSyncLocalTodoReminders(true)).toBe(false);
    expect(shouldSyncLocalTodoReminders(false)).toBe(true);
    expect(shouldSyncLocalTodoReminders(undefined)).toBe(true);
  });
});
