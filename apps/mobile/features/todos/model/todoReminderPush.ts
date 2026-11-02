/** Pure helpers for remote vs local todo-due notifications. */

export function isRemotePushTrigger(trigger: unknown): boolean {
  if (trigger == null || typeof trigger !== "object") return false;
  return (trigger as { type?: unknown }).type === "push";
}

export function todoIdFromNotificationData(
  data: Record<string, unknown> | null | undefined,
): string | null {
  if (!data) return null;
  const type = data.type;
  if (type !== "todo_due" && type !== "todo_reminder") return null;
  const id = data.todo_id;
  return typeof id === "string" && id.length > 0 ? id : null;
}

/**
 * The server sends due reminders only to a device that registered a push token with it;
 * the push setting alone says nothing about this device (Expo Go and a phone without
 * permission never register one). Schedule on the device unless the server holds its token.
 */
export function shouldSyncLocalTodoReminders(
  remotePushRegistered: boolean | null | undefined,
): boolean {
  return remotePushRegistered !== true;
}
