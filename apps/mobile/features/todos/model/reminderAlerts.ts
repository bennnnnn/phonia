/**
 * Whether a saved reminder can alert, asked at the moment the user saves one.
 *
 * Local reminders run only with notification permission, and a background refresh never
 * asks for it (todoReminders.permitted). On a fresh install where push was never turned
 * on, every reminder was skipped in silence. Saving a reminder with a time is an explicit
 * action, so that is when the app asks; a user who said no is told once per app launch.
 */
type ReminderAlerts = "on" | "off";

let toldAlertsOff = false;

export async function allowReminderAlerts(): Promise<ReminderAlerts> {
  try {
    // Loaded on save, so every chat bubble that holds a card does not load expo-notifications.
    const { ensureNotificationPermission } = await import("@/features/notifications/model/pushNotifications");
    return (await ensureNotificationPermission()) ? "on" : "off";
  } catch {
    return "off";
  }
}

/** True the first time alerts are off since launch, so the user is told only once. */
export function shouldTellAlertsOff(): boolean {
  if (toldAlertsOff) return false;
  toldAlertsOff = true;
  return true;
}

/** For tests: tell again. */
export function resetAlertsOffNotice(): void {
  toldAlertsOff = false;
}
