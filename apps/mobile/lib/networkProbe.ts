import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";

import { checkHealth } from "@/lib/api/connectivity";

/** Tiny captive-portal style check — proves the device has a working uplink
 * even when our API host is unreachable (wrong LAN IP, API down, etc.). */
const PUBLIC_REACHABILITY_URL = "https://clients3.google.com/generate_204";
const NETINFO_REFRESH_TIMEOUT_MS = 1_000;
const CONNECTIVITY_PROBE_TIMEOUT_MS = 3_500;

export type ConnectivityStatus = "online" | "no_internet" | "api_unreachable";

let netInfoConfigured = false;

/** Our own probe decides reachability. NetInfo's would add a HEAD to Google every 60 s (5 s
 * while unreachable) and one on every refresh. Call once, before subscribing. */
export function configureNetInfo(): void {
  if (netInfoConfigured) return;
  netInfoConfigured = true;
  NetInfo.configure({ reachabilityShouldRun: () => false });
}

function settleWithin<T>(promise: Promise<T>, timeoutMs: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout>;
    const finish = (value: T) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    timer = setTimeout(() => finish(fallback), timeoutMs);
    void promise.then(finish, () => finish(fallback));
  });
}

export async function checkPublicReachability(timeoutMs = 3_000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(PUBLIC_REACHABILITY_URL, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    // 204 is the ideal response; some networks rewrite to 200/204/redirect.
    return res.status === 204 || res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** API health wins: if Recall is up, we are online even when generate_204 is blocked. */
export function classifyConnectivity(apiOk: boolean, publicOk: boolean): ConnectivityStatus {
  if (apiOk) return "online";
  if (publicOk) return "api_unreachable";
  return "no_internet";
}

/**
 * Probe the API, then the public internet only if the API failed. Does not trust OS
 * "connected": that hid captive portals and API-down behind a missing banner.
 */
export async function resolveConnectivity(): Promise<ConnectivityStatus> {
  // NetInfo.refresh can remain unresolved after an iOS/simulator reconnect.
  // Give it a short chance, then probe regardless of the OS link report.
  await settleWithin<NetInfoState | null>(
    NetInfo.refresh(),
    NETINFO_REFRESH_TIMEOUT_MS,
    null,
  );

  const apiOk = await settleWithin(
    checkHealth(CONNECTIVITY_PROBE_TIMEOUT_MS),
    CONNECTIVITY_PROBE_TIMEOUT_MS,
    false,
  );
  if (apiOk) return "online";
  // Only now ask Google: is it our API, or the whole connection?
  const publicOk = await settleWithin(
    checkPublicReachability(CONNECTIVITY_PROBE_TIMEOUT_MS),
    CONNECTIVITY_PROBE_TIMEOUT_MS,
    false,
  );
  return classifyConnectivity(apiOk, publicOk);
}
