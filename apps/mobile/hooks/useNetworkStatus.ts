import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";

import { onConnectionAnswered, onConnectionFailure } from "@/lib/api/connectionFailures";
import { onAppStateChange } from "@/lib/foregroundRefresh";
import { isNetworkOffline } from "@/lib/networkStatus";
import { connectionLostAt, reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";
import {
  configureNetInfo,
  resolveConnectivity,
  type ConnectivityStatus,
} from "@/lib/networkProbe";

const FIRST_RETRY_MS = 1_500;
const MAX_RETRY_MS = 60_000;
const RETRY_JITTER = 0.2;
/** After a check failed requests asked for found the API answering, the next waits this long. */
const FAILURE_CHECK_QUIET_MS = MAX_RETRY_MS;

/**
 * The wait before degraded probe `attempt` (from 0): 1.5 s doubling to a minute, ±20%.
 * A fixed 1.5 s loop sent every foreground phone to /health 40 times a minute, in step,
 * for as long as the API looked down: just when it was recovering.
 */
export function retryDelayMs(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(MAX_RETRY_MS, FIRST_RETRY_MS * 2 ** attempt);
  return Math.round(base * (1 - RETRY_JITTER + 2 * RETRY_JITTER * random()));
}

/**
 * The address the link has, where the OS gives it without extra permission
 * (Wi-Fi and Ethernet): a switch straight from one Wi-Fi network to another
 * is a new link, though its type stays "wifi".
 */
function linkAddress(state: NetInfoState): string {
  const details = state.details;
  const address = details && "ipAddress" in details ? details.ipAddress : null;
  return typeof address === "string" ? address : "";
}

export function useNetworkStatus(): {
  isOffline: boolean;
  status: ConnectivityStatus;
} {
  const [status, setStatus] = useState<ConnectivityStatus>("online");
  // The degraded-state loop is for the banner on screen; it pauses in the
  // background and the return to "active" probes straight away. A launch in the
  // background (a push, a background task) starts there.
  const [inBackground, setInBackground] = useState(() => AppState.currentState === "background");
  // A link change or a return to the app starts the backoff over.
  const [retryEpoch, setRetryEpoch] = useState(0);
  // Bump to ignore in-flight probes after unmount or a newer event.
  const probeGen = useRef(0);
  // One probe at a time (each is two requests): start-up's fetch and the listener's
  // first call, or a return during the degraded loop, share the probe on its way.
  // A new link starts its own (`fresh`): one started on the old link says nothing.
  const inFlight = useRef<Promise<ConnectivityStatus> | null>(null);
  const probe = useCallback((fresh = false): Promise<ConnectivityStatus> => {
    if (fresh || !inFlight.current) {
      const run = resolveConnectivity().finally(() => {
        if (inFlight.current === run) inFlight.current = null;
      });
      inFlight.current = run;
    }
    return inFlight.current;
  }, []);
  const runProbe = useCallback((fresh: boolean) => {
    const gen = ++probeGen.current;
    void probe(fresh).then((next) => {
      if (gen !== probeGen.current) return;
      setStatus(next);
    });
  }, [probe]);

  useEffect(() => {
    configureNetInfo();
    // NetInfo repeats its report: once per subscription at launch, and again
    // after each probe's own refresh. Only a change of link, or the OS saying
    // the internet is unreachable, is news; its reachability check settling
    // to "reachable" just after launch is not.
    let lastLink: string | null = null;
    let lastOffline: boolean | null = null;

    const onNetInfo = (state: NetInfoState) => {
      const offline = isNetworkOffline(state);
      const link = `${state.type}:${offline}:${state.isInternetReachable === false}:${linkAddress(state)}`;
      if (link === lastLink) return;
      // The link coming back up drops a stale "No internet" banner at once (iOS
      // often leaves isInternetReachable stuck false). A report on a link that
      // stayed up does not: on Wi-Fi with no internet behind it, the probe that
      // just found that triggers one. Offline from NetInfo is often stale after
      // reconnect, so it never flips the banner on by itself.
      const cameUp = lastOffline === true && !offline;
      lastLink = link;
      lastOffline = offline;
      setRetryEpoch((epoch) => epoch + 1);
      if (cameUp) setStatus((prev) => (prev === "no_internet" ? "online" : prev));
      // Still probe a new link: connected Wi-Fi can be a captive portal or the
      // API can be down.
      runProbe(true);
    };

    void NetInfo.fetch().then(onNetInfo);
    const unsubscribe = NetInfo.addEventListener(onNetInfo);

    // Every return probes (FOREGROUND_STALE_MS.connectivity is 0); an iOS "inactive" blip is no return.
    const onAppState = (next: AppStateStatus, returned: boolean) => {
      setInBackground(next === "background");
      if (returned) {
        setRetryEpoch((epoch) => epoch + 1);
        runProbe(false);
      }
    };
    const stopAppState = onAppStateChange(onAppState);

    return () => {
      probeGen.current += 1;
      unsubscribe();
      stopAppState();
    };
  }, [runProbe]);

  // While degraded, keep probing so a reconnect clears the banner even when NetInfo
  // never emits an "online" event, backing off between probes.
  const degraded = status !== "online";
  useEffect(() => {
    if (!degraded || inBackground) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const waitThenProbe = (attempt: number) => {
      timer = setTimeout(() => {
        void probe().then((next) => {
          if (cancelled) return;
          setStatus(next);
          if (next !== "online") waitThenProbe(attempt + 1);
        });
      }, retryDelayMs(attempt));
    };
    waitThenProbe(0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [degraded, inBackground, retryEpoch, probe]);

  // A request that found no API (lib/api/connectionFailures.ts) asks for a check: an outage
  // that began with the app open showed no banner until a network change or a return, and the
  // list on screen was not read again when it ended. A burst of failures waits for one check,
  // the loop's first wait later. A check that finds the API answering (its database and Redis
  // too: a route failing on its own) holds the next off for a minute; one that finds an outage
  // (a dependency's too, lib/api/connectivity.ts) hands over to the loop, and once the banner
  // clears the next failure is a new outage. In the background nothing checks.
  const quietUntil = useRef(0);
  useEffect(() => {
    if (degraded) quietUntil.current = 0;
    if (degraded || inBackground) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const stopFailures = onConnectionFailure(() => {
      if (timer || Date.now() < quietUntil.current) return;
      timer = setTimeout(() => {
        timer = null;
        quietUntil.current = Date.now() + FAILURE_CHECK_QUIET_MS;
        runProbe(false);
      }, retryDelayMs(0));
    });
    return () => {
      stopFailures();
      if (timer) clearTimeout(timer);
    };
  }, [degraded, inBackground, runProbe]);

  // A request our API answered, sent after the outage was seen, is the API back: the banner
  // cleared at the loop's next check, up to a minute later, over a reply that had landed. A
  // check still on its way says nothing newer. One sent before the outage was seen proves nothing.
  useEffect(() => {
    if (!degraded || inBackground) return;
    return onConnectionAnswered((sentAt) => {
      if (sentAt <= connectionLostAt()) return;
      probeGen.current += 1;
      inFlight.current = null;
      setStatus("online");
    });
  }, [degraded, inBackground]);

  // The API answering again: the list on screen is read again (lib/reconnectRefresh.ts). Back
  // while the app is in the background, the return reads what every return does.
  const wasDegraded = useRef(false);
  useEffect(() => {
    if (degraded) {
      wasDegraded.current = true;
      reportDisconnected();
    } else if (wasDegraded.current) {
      wasDegraded.current = false;
      if (!inBackground) reportReconnected();
    }
  }, [degraded, inBackground]);

  // Going to the background and back changes nothing a reader sees.
  return useMemo(() => ({ isOffline: status !== "online", status }), [status]);
}
