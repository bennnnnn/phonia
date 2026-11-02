import Constants from "expo-constants";
import { AppState, Platform } from "react-native";

import { api, type ProductEventName } from "@/lib/api";
import { getSessionGeneration, getToken } from "@/lib/auth";
import { getInstallationId } from "@/lib/installationId";

/**
 * Metadata-only product events, sent in batches. Each chat turn used to post its two
 * events alone, every one a request and a commit (code-health audit NET-15). Now an
 * event waits in memory until a full batch is waiting, 30 s have passed since the
 * first one, the app goes to the background, or a rarer event (paywall, purchase,
 * push permission) goes out and takes the waiting ones with it. Analytics never
 * delays or fails the action it measures: a batch that fails to send is dropped.
 */

/** The most the server takes in one request (`ProductEventBatchIn`). */
export const PRODUCT_EVENT_BATCH = 20;
export const PRODUCT_EVENT_FLUSH_MS = 30_000;
/** Kept while offline; beyond this the oldest are dropped. */
const MAX_WAITING = 100;
/** Sent with the next batch; every other event goes out at once. */
const BATCHED: ReadonlySet<ProductEventName> = new Set(["chat_ttft", "chat_turn_outcome"]);

type WaitingEvent = {
  /** The sign-in session that recorded it: a later account never sends it. */
  generation: number;
  name: ProductEventName;
  properties: Record<string, string>;
  platform: "ios" | "android";
  client_at: string;
};

let waiting: WaitingEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let flushOnBackground = false;

function analyticsPlatform(): WaitingEvent["platform"] | null {
  if (Platform.OS === "ios" || Platform.OS === "android") {
    return Platform.OS;
  }
  return null;
}

function watchBackground(): void {
  if (flushOnBackground) return;
  flushOnBackground = true;
  AppState.addEventListener("change", (state) => {
    if (state === "background") void flushProductEvents();
  });
}

/** Record a metadata-only product event (fire-and-forget). */
export function trackProductEvent(
  name: ProductEventName,
  properties: Record<string, string> = {},
): void {
  const platform = analyticsPlatform();
  if (!platform) return;
  waiting.push({
    generation: getSessionGeneration(),
    name,
    properties,
    platform,
    client_at: new Date().toISOString(),
  });
  if (waiting.length > MAX_WAITING) waiting = waiting.slice(-MAX_WAITING);
  watchBackground();
  if (!BATCHED.has(name) || waiting.length >= PRODUCT_EVENT_BATCH) {
    void flushProductEvents();
  } else if (!flushTimer) {
    flushTimer = setTimeout(() => void flushProductEvents(), PRODUCT_EVENT_FLUSH_MS);
  }
}

/** Send what is waiting now, in batches of `PRODUCT_EVENT_BATCH`. */
export async function flushProductEvents(): Promise<void> {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  const generation = getSessionGeneration();
  const events = waiting.filter((event) => event.generation === generation);
  waiting = [];
  if (events.length === 0) return;
  try {
    const token = await getToken();
    if (!token || generation !== getSessionGeneration()) return;
    const installationId = (await getInstallationId()) ?? undefined;
    const appVersion = Constants.expoConfig?.version;
    for (let start = 0; start < events.length; start += PRODUCT_EVENT_BATCH) {
      await api.recordProductEvents(
        token,
        events.slice(start, start + PRODUCT_EVENT_BATCH).map(({ generation: _, ...event }) => ({
          ...event,
          app_version: appVersion,
          installation_id: installationId,
        })),
      );
    }
  } catch {
    // Best-effort by design; product telemetry never blocks the app.
  }
}
