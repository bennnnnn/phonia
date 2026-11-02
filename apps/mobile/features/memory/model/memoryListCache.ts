import { api, type Memory } from "@/lib/api";
import { onAppEvent } from "@/lib/appEvents";
import { CONTEXT_REFRESH_STALE_MS } from "@/lib/cache/contextRefresh";
import {
  SessionResourceCache,
  type FailureReporter,
  type ResourceResult,
  type ResourceUpdate,
} from "@/lib/cache/sessionResource";

const LIST = "memories";
const resource = new SessionResourceCache<typeof LIST, Memory[]>({
  staleMs: CONTEXT_REFRESH_STALE_MS,
  empty: () => [],
  sessionState: () => undefined,
});

export function subscribeMemoriesCache(listener: () => void): () => void {
  return resource.subscribe(listener);
}

export function getCachedMemories(): Memory[] | undefined {
  return resource.get(LIST);
}

export function isMemoriesFresh(): boolean {
  return resource.isFresh(LIST);
}

/** When the list last came from the server this sign-in. */
export function memoriesReadAt(): number | undefined {
  return resource.fetchedAt(LIST);
}

export function setMemoriesCache(data: Memory[], expectedSession?: number): void {
  resource.set(LIST, data, expectedSession);
}

/** Apply a pure row update now and replay it over any already-running list read. */
export function updateMemoriesCache(update: ResourceUpdate<Memory[]>, expectedSession?: number): Memory[] {
  return resource.update(LIST, update, expectedSession) ?? [];
}

export function invalidateMemoriesCache(): void {
  resource.invalidate();
}
// Memory cleared or turned off from a chat's settings card: the list reads fresh.
onAppEvent("memoryChanged", invalidateMemoriesCache);

export function fetchMemories(
  token: string,
  opts?: { force?: boolean; afterPending?: boolean; report?: FailureReporter },
): Promise<ResourceResult<Memory[]>> {
  return resource.fetch(LIST, token, () => api.listMemories(token), opts);
}

/** Warm the list so /memory can paint without a skeleton. */
export function prefetchMemories(token: string): void {
  void fetchMemories(token);
}
