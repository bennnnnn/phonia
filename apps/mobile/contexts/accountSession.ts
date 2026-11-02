/**
 * The signed-in account, for effects to key on, and its newest bearer token, read when a
 * request goes out. The token rotates hourly; keyed on it, effects re-fetched the model
 * list, the usage and the location, restarted downloads and made a new draft chat every
 * hour (code-health audit NET-11). `account` changes only on sign-in, sign-out and an
 * account switch. `AuthProvider` provides it; no imports, so a hook reads it without the
 * sign-in stack.
 */

import { createContext, useContext } from "react";

type AccountSession = { account: string | null; getToken: () => string | null };

export const AccountSessionContext = createContext<AccountSession>({
  account: null,
  getToken: () => null,
});

export function useAccountSession(): AccountSession {
  return useContext(AccountSessionContext);
}
