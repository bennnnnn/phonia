import { useCallback, useEffect, useState } from "react";

import { getSessionGeneration } from "@/lib/auth";
import {
  ensureNotificationPermission,
  getNotificationPermissionGranted,
  registerRemotePushToken,
  unregisterRemotePushToken,
} from "@/features/notifications/model/pushNotifications";

type PushNotificationToggleOptions = {
  token: string | null;
  serverEnabled: boolean;
  isCurrentView: () => boolean;
  updatePreference: (enabled: boolean) => Promise<void>;
  acquireMutation: () => (() => void) | null;
  onPermissionDenied: () => void;
  onError: () => void;
};

/**
 * Owns the push switch's optimistic draft without letting a stale screen or
 * previous account update the current view.
 */
export function usePushNotificationToggle({
  token,
  serverEnabled,
  isCurrentView,
  updatePreference,
  acquireMutation,
  onPermissionDenied,
  onError,
}: PushNotificationToggleOptions) {
  const session = getSessionGeneration();
  const [permissionGranted, setPermissionGranted] = useState<boolean | null>(null);
  const [optimisticValue, setOptimisticValue] = useState<boolean | null>(null);

  const sameAccount = useCallback(
    () => Boolean(token) && session === getSessionGeneration(),
    [session, token],
  );
  const isCurrent = useCallback(
    () => isCurrentView() && sameAccount(),
    [isCurrentView, sameAccount],
  );

  useEffect(() => {
    if (!isCurrent()) return;
    let active = true;
    void getNotificationPermissionGranted()
      .then((granted) => {
        if (active && isCurrent()) setPermissionGranted(granted);
      })
      .catch(() => {
        if (!active || !isCurrent()) return;
        setPermissionGranted(false);
        onError();
      });
    return () => {
      active = false;
    };
  }, [isCurrent, onError]);

  const value = optimisticValue ?? (serverEnabled && permissionGranted === true);

  const setDenied = useCallback(async () => {
    if (isCurrent()) {
      setPermissionGranted(false);
      setOptimisticValue(false);
      onPermissionDenied();
    }
    if (serverEnabled && sameAccount()) {
      await updatePreference(false);
    }
  }, [isCurrent, onPermissionDenied, sameAccount, serverEnabled, updatePreference]);

  const toggle = useCallback(async (enabled: boolean) => {
    if (!token || !isCurrent()) return;
    const release = acquireMutation();
    if (!release) return;
    setOptimisticValue(enabled);

    try {
      if (!enabled) {
        await updatePreference(false);
        if (sameAccount()) await unregisterRemotePushToken(token);
        return;
      }

      const granted = await ensureNotificationPermission();
      if (!sameAccount()) return;
      if (!granted) {
        await setDenied();
        return;
      }

      if (isCurrent()) setPermissionGranted(true);
      const registration = await registerRemotePushToken(token, true);
      if (!sameAccount()) return;
      if (registration === "disabled_permission") {
        await setDenied();
        return;
      }
      await updatePreference(true);
    } catch {
      if (isCurrent()) onError();
    } finally {
      if (isCurrent()) setOptimisticValue(null);
      release();
    }
  }, [
    acquireMutation,
    isCurrent,
    onError,
    sameAccount,
    setDenied,
    token,
    updatePreference,
  ]);

  return { value, permissionGranted, toggle };
}
