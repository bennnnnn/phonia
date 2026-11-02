import { useCallback } from "react";
import { Platform } from "react-native";

import { useAuth } from "@/contexts/AuthContext";
import { type AccountDeleteFailure, accountDeleteFailure, isAccountDeleteComplete } from "@/lib/accountDelete";
import { api } from "@/lib/api";
import { appleConsentForAccountDelete } from "@/lib/apple-auth";

/**
 * "cancelled": the user closed the Sign in with Apple sheet, so nothing was deleted.
 * "unavailable": Recall could not serve the delete for now; nothing was deleted.
 */
export type AccountDeleteOutcome = "deleted" | "cancelled" | AccountDeleteFailure;

/**
 * Delete the account, then sign out: Settings → Data controls and the AI consent screen
 * (a user who has not agreed cannot reach Settings) share this one path. An Apple-linked
 * account on iOS asks Apple first, so the server can revoke the grant. `onStart` runs
 * once the request is about to go out.
 */
export function useAccountDelete(): (onStart?: () => void) => Promise<AccountDeleteOutcome> {
  const { token, user, signOut, setIgnoreUnauthorized } = useAuth();
  const appleLinked = Boolean(user?.apple_linked);

  return useCallback(
    async (onStart) => {
      if (!token) return "failed";
      let appleCode: string | null = null;
      if (Platform.OS === "ios" && appleLinked) {
        const consent = await appleConsentForAccountDelete();
        if (consent.kind === "cancelled") return "cancelled";
        appleCode = consent.kind === "code" ? consent.code : null;
      }
      onStart?.();
      setIgnoreUnauthorized(true);
      try {
        try {
          await api.deleteAccount(token, appleCode);
        } catch (error) {
          if (!isAccountDeleteComplete(error)) throw error;
        }
        await signOut();
        return "deleted";
      } catch (error) {
        setIgnoreUnauthorized(false);
        return accountDeleteFailure(error);
      }
    },
    [appleLinked, setIgnoreUnauthorized, signOut, token],
  );
}
