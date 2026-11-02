import type { NetInfoState } from "@react-native-community/netinfo";

/**
 * Offline when the OS link is down, or reachability is unknown and reported bad.
 * When the link is up (isConnected === true), always online — iOS/simulator often
 * leaves isInternetReachable stuck false after reconnect.
 */
export function isNetworkOffline(state: NetInfoState): boolean {
  if (state.isConnected === true) return false;
  if (state.isConnected === false) return true;
  return state.isInternetReachable === false;
}

/** NetInfo's type before the OS has reported a link (the enum is not imported: no native module in Node). */
const UNKNOWN_LINK: string = "unknown";

/** The device's address on Wi-Fi or Ethernet, when the platform reports it. */
function localAddress(state: NetInfoState): string | null {
  const details = state.details;
  if (!details || !("ipAddress" in details)) return null;
  return typeof details.ipAddress === "string" ? details.ipAddress : null;
}

/**
 * The device went offline, came back, or moved to another network (Wi-Fi ⇄
 * cellular, another Wi-Fi): a connection opened on the old path may be
 * half-open. The first report, a first link after "unknown", and details of the
 * same link (signal, reachability probes) are not changes.
 */
export function isNetworkPathChange(previous: NetInfoState | null, next: NetInfoState): boolean {
  if (!previous) return false;
  if (isNetworkOffline(previous) !== isNetworkOffline(next)) return true;
  if (previous.type === UNKNOWN_LINK || next.type === UNKNOWN_LINK) return false;
  if (previous.type !== next.type) return true;
  const before = localAddress(previous);
  const after = localAddress(next);
  return before !== null && after !== null && before !== after;
}
