import { api, type Usage } from "@/lib/api";
import { CONTEXT_REFRESH_STALE_MS } from "@/lib/cache/contextRefresh";
import { StaleResourceCache } from "@/lib/cache/staleResource";

/** Keyed by account, not bearer token: the token rotates hourly (code-health audit NET-11). */
const resource = new StaleResourceCache<string, Usage>(CONTEXT_REFRESH_STALE_MS);

export function getCachedUsage(account: string): Usage | undefined {
  return resource.get(account);
}

/** When the account's usage last came from the server. */
export function usageReadAt(account: string): number | undefined {
  return resource.getFetchedAt(account);
}

export function invalidateUsageCache(): void {
  resource.clear();
}

export async function fetchTodayUsage(
  account: string,
  token: string,
  opts?: { force?: boolean },
): Promise<Usage | null> {
  try {
    return await resource.fetch(account, () => api.todayUsage(token), opts);
  } catch {
    return null;
  }
}
