/** Strip server-side ```reminder fences from live chat (DB already strips on persist). */

import { stripLangFence } from "@/lib/mdFenceScan";

// The fence's language is exactly "reminder": a ```reminder_proposal card is drawn, not stripped.
export function stripReminderFences(content: string): string {
  return stripLangFence(content, "reminder")
    .replace(/\n{3,}/g, "\n\n")
    .trimEnd();
}
