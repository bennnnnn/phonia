import { useEffect, useRef, useState } from "react";

import { useAuthOptional } from "@/contexts/AuthContext";
import { api, type RecurrenceRule, type Todo } from "@/lib/api";

/** How long a picked due time stays before its reminder time is asked for. */
const PREVIEW_DELAY_MS = 300;

export type RemindAt =
  /** No reminder: no due time, or the server sends none (more than 48 hours past due). */
  | { status: "none" }
  | { status: "at"; at: Date }
  /** Not known yet: the server is being asked, or could not be. */
  | { status: "unknown" };

type Preview = { key: string; result: RemindAt };

const NONE: RemindAt = { status: "none" };
const UNKNOWN: RemindAt = { status: "unknown" };

function remindAtOf(notifyAt: string | null | undefined): RemindAt {
  return notifyAt ? { status: "at", at: new Date(notifyAt) } : NONE;
}

/**
 * The editor's "Remind at": when the to-do's reminder goes out, as the server works it out
 * (the lead time, after quiet hours), the moment push and the phone's own alert fire. While
 * the due time and repeat are the saved ones, the saved to-do's `notify_at` (no request);
 * for ones the editor has not saved, the server's preview of the save, asked once they have
 * stayed for PREVIEW_DELAY_MS, and again when the profile's lead time, quiet hours or zone
 * changes. The phone works out nothing.
 */
export function useRemindAt({
  dueDate,
  repeat,
  saved,
  enabled,
}: {
  dueDate: Date | null;
  repeat: RecurrenceRule | null;
  /** The to-do as the list holds it now; none for a new one. */
  saved?: Todo | null;
  enabled: boolean;
}): RemindAt {
  const auth = useAuthOptional();
  const tokenRef = useRef(auth?.token ?? null);
  tokenRef.current = auth?.token ?? null;
  const user = auth?.user;
  const profile = user
    ? [user.reminder_lead_minutes, user.quiet_hours_enabled, user.quiet_hours_start_minute,
      user.quiet_hours_end_minute, user.timezone].join("|")
    : "";
  const dueIso = dueDate ? dueDate.toISOString() : null;
  const asSaved = Boolean(saved?.due_at && dueIso && Date.parse(saved.due_at) === Date.parse(dueIso)
    && (saved.recurrence_rule ?? null) === repeat);
  const key = enabled && dueIso && !asSaved ? `${dueIso}|${repeat ?? ""}|${profile}` : null;
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    if (!key || !dueIso) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const token = tokenRef.current;
      if (!token) return;
      api.previewReminder(token, dueIso, repeat, controller.signal)
        .then(({ notify_at }) => {
          if (!controller.signal.aborted) setPreview({ key, result: remindAtOf(notify_at) });
        })
        .catch(() => {
          if (!controller.signal.aborted) setPreview({ key, result: UNKNOWN });
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key, dueIso, repeat]);

  if (!dueIso) return NONE;
  if (asSaved) return remindAtOf(saved?.notify_at);
  return preview && preview.key === key ? preview.result : UNKNOWN;
}
