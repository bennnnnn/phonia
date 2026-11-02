import { getApiUrl } from "@/lib/config";

import { apiUrl } from "@/lib/api/client";
import { newRequestId, REQUEST_ID_HEADER } from "@/lib/api/requestId";

export function chatWebSocketUrl(chatId: string) {
  const base = getApiUrl().replace(/^http/, "ws");
  return `${base}/ws/chats/${chatId}`;
}

/**
 * Whether the API can serve: its database and Redis answer too. /health is liveness only and
 * answered 200 through their outage while every read failed, so the check found "online": no
 * banner, and nothing read again when the outage ended. The server keeps this answer a few
 * seconds, however many phones ask.
 */
export async function checkHealth(timeoutMs = 4000): Promise<boolean> {
  // AbortController + timeout so a hung network (e.g. a captive portal that
  // holds the connection open without responding) doesn't pile up overlapping
  // fetches when this is polled while the offline banner is visible. The timer
  // is cleared in `finally` so a rejected/aborted fetch never leaks it.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(apiUrl("/health/dependencies"), {
      signal: controller.signal,
      headers: { [REQUEST_ID_HEADER]: newRequestId() },
    });
    // An API from before this route (a rollback, or an app update shipped before the API's)
    // answers 404: it is up, as /health would have said. Every phone showed the banner else.
    return res.ok || res.status === 404;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
