import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { getDeviceTimezone } from "@/lib/deviceTimezone";
import { getDeviceLocationLabel } from "@/lib/deviceLocation";
import { configurePurchases, isPurchasesConfigured, registerPlanChangeListener } from "@/features/billing/model/purchases";
import { getSessionGeneration } from "@/lib/auth";
import { api, type User } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { recentSyncAt, recordSync } from "@/lib/syncRecords";
import { emitAppEvent } from "@/lib/appEvents";
import { onPhoneClockChange } from "@/lib/datetime/phoneClock";
import { onAppStateChange } from "@/lib/foregroundRefresh";
import { trackZoneReport } from "@/lib/zoneReport";

type Options = {
  token: string | null;
  user: User | null;
  setUser: Dispatch<SetStateAction<User | null>>;
};

/** The zone report this hook keeps across its effect's runs (see the zone effect). */
type ZoneReport = {
  flight: Promise<void> | null;
  /** Something asked for a report while one was in flight. */
  again: boolean;
  /** A zone the server refused as unknown. */
  refused: string | null;
  /** The current run's report, which a report that lands calls when asked `again`. */
  latest: (() => void) | null;
};

/** A GPS fix and a reverse geocode for a city label: once a day is enough. */
const LOCATION_SYNC_INTERVAL_MS = 24 * 60 * 60_000;

/** Post-login side effects — timezone, location, push sync, RevenueCat. */
export function useBootstrapSync({ token, user, setUser }: Options): void {
  const userId = user?.id;
  const timezone = user?.timezone;
  const location = user?.location;
  const locationEnabled = user?.location_enabled;
  const pushEnabled = user?.push_notifications_enabled ?? false;
  const feedback = useActionFeedbackOptional();
  // Keyed on the sign-in, not the token: the access token refreshes hourly, and each
  // sync reads the newest one from this ref (code-health audit NET-11). On the token,
  // the location sync took a GPS fix and a reverse geocode every hour.
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const signedIn = Boolean(token);
  // The zone the server has: the profile's, or the one its last answer gave.
  const serverZone = useRef(timezone);
  serverZone.current = timezone;
  const zoneReport = useRef<ZoneReport>({ flight: null, again: false, refused: null, latest: null });
  // The phone's zone, sent the moment it differs from the server's: at sign-in, when the OS
  // reports a change (a new zone while the app runs) and on each return to the foreground
  // (a flight). Quiet hours, push timing and every to-do's notify_at read the server's copy.
  useEffect(() => {
    if (!signedIn || !userId) return;
    const generation = getSessionGeneration();
    let cancelled = false;
    const active = () => !cancelled && generation === getSessionGeneration();
    const state = zoneReport.current;
    const report = (): void => {
      if (!active()) return;
      // One report at a time; the zone is read again once it lands.
      if (state.flight) {
        state.again = true;
        return;
      }
      const deviceTz = getDeviceTimezone();
      const token = tokenRef.current;
      if (!token || deviceTz === serverZone.current || deviceTz === state.refused) return;
      const flight = (async () => {
        try {
          const updated = await api.updateMe(token, { timezone: deviceTz });
          if (!active()) return;
          serverZone.current = updated.timezone;
          setUser((current) => current?.id === userId
            ? { ...current, timezone: updated.timezone } : current);
          emitAppEvent("userUpdated", { fields: ["timezone"] });
        } catch (error) {
          // A name the server does not know is not sent again on every return.
          if (error instanceof ApiRequestError && error.status === 422) state.refused = deviceTz;
          if (active()) console.warn("[bootstrap] timezone sync failed");
        } finally {
          state.flight = null;
          if (state.again) {
            state.again = false;
            state.latest?.();
          }
        }
      })();
      state.flight = flight;
      trackZoneReport(flight);
    };
    state.latest = report;
    report();
    const stopNative = onPhoneClockChange(report);
    const stopForeground = onAppStateChange((_state, returned) => {
      if (returned) report();
    });
    return () => {
      cancelled = true;
      if (state.latest === report) state.latest = null;
      stopNative();
      stopForeground();
    };
  }, [signedIn, userId, timezone, setUser]);

  useEffect(() => {
    if (!signedIn || !userId || !locationEnabled) return;
    const generation = getSessionGeneration();
    let cancelled = false;
    const active = () => !cancelled && generation === getSessionGeneration();
    void (async () => {
      if (!active()) return;
      // The server keeps the label between reads; without one, read it now.
      if (location && (await recentSyncAt("location", userId, LOCATION_SYNC_INTERVAL_MS)) !== null) return;
      if (!active()) return;
      const label = await getDeviceLocationLabel();
      const current = tokenRef.current;
      if (!active() || !label || !current) return;
      const updated = location === label ? null : await api.updateMe(current, { location: label });
      if (!active()) return;
      // Recorded before the new label re-runs this effect, so that run finds it.
      await recordSync("location", userId);
      if (!active() || !updated) return;
      setUser((latest) => latest?.id === userId
        ? { ...latest, location: updated.location } : latest);
    })().catch(() => {
      if (active()) console.warn("[bootstrap] location sync failed");
    });
    return () => { cancelled = true; };
  }, [signedIn, userId, location, locationEnabled, setUser]);

  useEffect(() => {
    if (!signedIn || !userId) return;
    const generation = getSessionGeneration();
    let cancelled = false;
    let cleanup: (() => void) | undefined;
    void import("@/features/notifications/model/pushNotifications").then(({ attachPushForegroundSync }) => {
      const token = tokenRef.current;
      if (cancelled || generation !== getSessionGeneration() || !token) return;
      // Gate push registration on user.push_notifications_enabled — without
      // this, the backend holds a live push token for a user who opted out
      // and keeps sending them notifications. When disabled, the sync
      // unregisters the token instead of registering it.
      cleanup = attachPushForegroundSync(
        token,
        pushEnabled,
        (enabled) => {
          if (cancelled || generation !== getSessionGeneration()) return;
          setUser((current) => current?.id === userId
            ? { ...current, push_notifications_enabled: enabled } : current);
        },
        // Hourly token refreshes and cold starts re-attach; one sync per account
        // every 12 hours is enough.
        userId,
        feedback,
      );
    }).catch(() => {});
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [signedIn, userId, pushEnabled, setUser, feedback]);

  // RevenueCat is set up once per signed-in user; the plan sync reads the newest token.
  useEffect(() => {
    if (!signedIn || !userId) return;
    const generation = getSessionGeneration();
    let cancelled = false;
    const active = () => !cancelled && generation === getSessionGeneration();
    let cleanup: (() => void) | undefined;
    void (async () => {
      if (!active() || !isPurchasesConfigured()) return;
      await configurePurchases(userId);
      if (!active()) return;
      // Keep the backend plan in sync when the entitlement changes
      // (purchase / restore / expiry). The webhook may fail or lag; this
      // listener closes the gap without relying on a manual sync. The REST
      // call auto-refreshes the access token on 401, so a stale token is
      // fine.
      cleanup =
        (await registerPlanChangeListener(() => {
          if (!active()) return;
          // M3: merge only the plan's fields — setUser replaces the entire
          // user object and bypasses the generation guard in updateUser,
          // so a slow sync can overwrite an in-flight profile patch (e.g.
          // timezone toggle snaps back).
          const current = tokenRef.current;
          if (!current) return;
          void api
            .syncSubscription(current)
            .then((updated) => {
              if (!active()) return;
              // The plan and what it unlocks travel together, or locks stay wrong
              // until the next /auth/me.
              setUser((prev) => prev?.id === userId
                ? { ...prev, plan: updated.plan, features: updated.features } : prev);
            })
            .catch(() => {});
        })) ?? undefined;
      if (!active()) {
        cleanup?.();
        cleanup = undefined;
      }
    })().catch(() => {});
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [signedIn, userId, setUser]);
}
