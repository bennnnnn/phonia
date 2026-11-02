import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SetStateAction,
} from "react";

import {
  api,
  loginWithApple,
  loginWithDev,
  loginWithGoogle,
  logoutSession,
  setConsentRequiredHandler,
  setTokenRefreshHandler,
  setUnauthorizedHandler,
  type User,
  type AuthResult,
} from "@/lib/api";
import { accessTokenNeedsRefresh, freshAccessToken, refreshedAccount } from "@/lib/api/client";
import { signInWithAppleCredentials } from "@/lib/apple-auth";
import { signInWithGoogleIdToken } from "@/lib/google-auth";
import { ensureLocale } from "@/lib/i18n";
import {
  clearOnboarded,
  clearToken,
  CorruptSessionError,
  getOnboarded,
  getRefreshToken,
  getSessionGeneration,
  invalidateSession,
  getToken,
  setOnboarded,
  setTokenPair,
} from "@/lib/auth";
import { cachedUserMatchesToken, clearCachedUser, mergeCachedUser, readCachedUser, writeCachedUser } from "@/lib/cachedUser";
import { AccountSessionContext } from "@/contexts/accountSession";
import { reportCorruptSessionCleared } from "@/lib/sentry";
import { clearSignedOutAccount } from "@/lib/signOutCleanup";
import { forgetSyncRecords } from "@/lib/syncRecords";
import { emitAppEvent } from "@/lib/appEvents";
import { tokenSubject } from "@/lib/tokenSubject";
import { useBootstrapSync } from "@/hooks/useBootstrapSync";
import { AuthLoadingShell } from "@/components/AuthLoadingShell";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  loading: boolean;
  /** The user came from the server this run (sign-in, /auth/me or a profile
   * write), not only the launch cache, whose plan always reads "free". */
  profileValidated: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  signInWithDev: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Show the account `read` returns (`/auth/me` by default): a call that returns it,
   * such as a subscription sync, passes itself and saves a second request. */
  refreshUser: (read?: (token: string) => Promise<User>) => Promise<void>;
  updateUser: (patch: Partial<User>) => Promise<void>;
  mergeUser: (patch: Partial<User>) => void;
  onboarded: boolean;
  completeOnboarding: () => Promise<void>;
  /** Pause 401→signOut (account wipe purges sessions before the DELETE finishes). */
  setIgnoreUnauthorized: (value: boolean) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Token-only bag so chat list cells don't re-render on every user/quota patch. */
type AuthTokenBag = { token: string | null };
const AuthTokenContext = createContext<AuthTokenBag | null>(null);
/** Never changes: reads the signed-in user when called, for event handlers in list rows. */
const AuthUserReaderContext = createContext<(() => User | null) | null>(null);

type AuthProviderProps = {
  children: ReactNode;
  /** The launch restore has settled: the app, the sign-in or the retry screen can show. */
  onRestored?: () => void;
};

/** The stored access token; `corrupt` when a record is there but is no session. */
async function readStoredSession(): Promise<{ token: string | null; corrupt: boolean }> {
  try {
    return { token: await getToken(), corrupt: false };
  } catch (error) {
    if (error instanceof CorruptSessionError) return { token: null, corrupt: true };
    throw error;
  }
}

/** The account a failed launch read, for its Sign out: who to clear, which session to end. */
type LaunchSession = { userId: string | undefined; accessToken: string | null };
const NO_LAUNCH_SESSION: LaunchSession = { userId: undefined, accessToken: null };

export function AuthProvider({ children, onRestored }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [startupFailed, setStartupFailed] = useState(false);
  const [hydrationAttempt, setHydrationAttempt] = useState(0);
  const [onboarded, setOnboardedState] = useState(false);
  const [profileValidated, setProfileValidated] = useState(false);
  const userRef = useRef<User | null>(null);
  const tokenRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const localCleanupRef = useRef<Promise<void>>(Promise.resolve());
  const ignoreUnauthorizedRef = useRef(false);
  const updateUserGenRef = useRef(0);
  const launchSessionRef = useRef<LaunchSession>(NO_LAUNCH_SESSION);

  // Keep event-time identity current even before React paints a signout.
  const setCurrentUser = useCallback((value: SetStateAction<User | null>) => {
    const next = typeof value === "function" ? value(userRef.current) : value;
    userRef.current = next;
    setUser(next);
  }, []);
  const setCurrentToken = useCallback((value: string | null) => {
    tokenRef.current = value;
    setTokenState(value);
  }, []);
  const isCurrent = useCallback((generation: number) =>
    mountedRef.current && generation === getSessionGeneration(), []);

  const setIgnoreUnauthorized = useCallback((value: boolean) => {
    ignoreUnauthorizedRef.current = value;
  }, []);

  /**
   * Ends the session on this phone: its credentials and account data at once,
   * the server's copy best-effort. `keepOnboarded` opens on sign-in itself
   * rather than the introduction before it.
   */
  const endSession = useCallback((
    userId: string | undefined,
    accessToken: string | null,
    keepOnboarded = false,
  ) => {
    const refreshToken = getRefreshToken().catch(() => null);
    // clearToken invalidates the shared session synchronously before its disk
    // write, fencing refreshes, startup requests and pending login attempts.
    const clearCredentials = clearToken();
    setCurrentToken(null);
    setCurrentUser(null);
    setProfileValidated(false);
    if (!keepOnboarded) setOnboardedState(false);
    setLoading(false);
    setStartupFailed(false);
    ignoreUnauthorizedRef.current = false;
    launchSessionRef.current = NO_LAUNCH_SESSION;
    const cleanup = Promise.allSettled([
      clearCredentials,
      clearCachedUser(),
      keepOnboarded ? undefined : clearOnboarded(),
      localCleanupRef.current.catch(() => {}),
      clearSignedOutAccount(userId),
    ]).then((results) => {
      // Even a credential-store failure must wait for every local cleanup;
      // otherwise a new login can race a still-running old-account deletion.
      const credentials = results[0];
      if (credentials.status === "rejected") throw credentials.reason;
    });
    localCleanupRef.current = cleanup;
    if (accessToken) {
      // The device's push token goes with the logout, or this account's reminders keep
      // arriving on a signed-out phone. A failure to read it never holds the logout.
      const pushToken = import("@/features/notifications/model/pushNotifications")
        .then(({ devicePushToken }) => devicePushToken())
        .catch(() => null);
      void Promise.all([refreshToken, pushToken])
        .then(([refresh, push]) => logoutSession(accessToken, refresh, push))
        .catch(() => {});
    }
    return cleanup;
  }, [setCurrentToken, setCurrentUser]);

  const signOut = useCallback(
    () => endSession(userRef.current?.id, tokenRef.current),
    [endSession],
  );

  /** A launch that could not finish: sign out of the session it read, as Settings would. */
  const signOutFromLaunch = useCallback(() => {
    const { userId, accessToken } = launchSessionRef.current;
    return endSession(userId, accessToken);
  }, [endSession]);

  useEffect(() => {
    mountedRef.current = true;
    const generation = getSessionGeneration();
    let cancelled = false;
    const current = () => !cancelled && isCurrent(generation);
    let hasCachedAccount = false;
    launchSessionRef.current = NO_LAUNCH_SESSION;
    void (async () => {
      try {
        const [read, onb, cachedUser] = await Promise.all([
          readStoredSession(), getOnboarded(), readCachedUser(),
        ]);
        if (!current()) return;
        setOnboardedState(onb);
        const stored = read.token;
        const cacheIsThisAccount = Boolean(
          stored && cachedUser && cachedUserMatchesToken(cachedUser, stored),
        );
        if (cachedUser && !cacheIsThisAccount) {
          // Left by another account, or a sign-out whose delete failed. Its
          // language was applied before the first render (lib/launchPrefs.ts).
          void clearCachedUser();
          void ensureLocale("en");
        }
        if (read.corrupt) {
          // No retry can read it (it once left "error, Retry" for good, and the
          // iOS keychain keeps it through a reinstall): clear it with this
          // phone's account data, and open on sign-in. Counted, never described.
          endSession(cachedUser?.id, null, true).catch(() => {
            console.warn("[auth] could not clear an unreadable sign-in");
          });
          reportCorruptSessionCleared();
          return;
        }
        if (!stored) return;
        // Read only to clear this account's local data if its Sign out is pressed.
        launchSessionRef.current = { userId: tokenSubject(stored) ?? undefined, accessToken: stored };
        if (cachedUser && cacheIsThisAccount) {
          hasCachedAccount = true;
          setCurrentToken(stored);
          setCurrentUser(mergeCachedUser(cachedUser));
          setLoading(false);
        }
        const revision = updateUserGenRef.current;
        // An expired token is refreshed first, and the refresh answers with the account.
        const refreshed = accessTokenNeedsRefresh(stored) ? await freshAccessToken(stored) : null;
        if (!current()) return;
        const me = refreshedAccount(refreshed) ?? await api.me(stored);
        // /me may have rotated credentials. Never put the startup token back.
        const currentToken = await getToken();
        if (!current() || !currentToken) return;
        setCurrentToken(currentToken);
        if (revision === updateUserGenRef.current) {
          setCurrentUser(me);
          setProfileValidated(true);
          void writeCachedUser(me);
        }
      } catch {
        // Offline launches retain a cached account. Without one, keep a
        // recoverable startup screen: read/network failures are not logout.
        if (current() && !hasCachedAccount) setStartupFailed(true);
      } finally {
        if (current()) setLoading(false);
      }
    })();
    return () => { cancelled = true; mountedRef.current = false; };
  }, [hydrationAttempt, isCurrent, setCurrentToken, setCurrentUser, endSession]);

  const restored = !loading || startupFailed;
  useEffect(() => {
    if (restored) onRestored?.();
  }, [restored, onRestored]);

  const retryStartup = useCallback(() => {
    setStartupFailed(false);
    setLoading(true);
    setHydrationAttempt((attempt) => attempt + 1);
  }, []);

  const signIn = useCallback(async (login: (current: () => boolean) => Promise<AuthResult | null>) => {
    const generation = invalidateSession();
    ignoreUnauthorizedRef.current = false;
    await localCleanupRef.current.catch(() => {});
    if (!isCurrent(generation)) return;
    const result = await login(() => isCurrent(generation));
    if (!result || !isCurrent(generation)) return;
    // A crash between the credential write and cache write must not pair a
    // newly signed-in account's token with the previous account's display,
    // and a sync record a sign-out failed to delete must not skip this
    // sign-in's push registration (lib/syncRecords.ts).
    await Promise.all([clearCachedUser(), forgetSyncRecords()]);
    if (!isCurrent(generation)) return;
    const saved = await setTokenPair(result.access_token, result.refresh_token, generation);
    if (!saved || !isCurrent(generation)) return;
    setCurrentToken(result.access_token);
    setCurrentUser(result.user);
    setProfileValidated(true);
    setLoading(false);
    void writeCachedUser(result.user);
  }, [isCurrent, setCurrentToken, setCurrentUser]);

  const signInWithGoogle = useCallback(() => signIn(async (current) => {
    const idToken = await signInWithGoogleIdToken();
    return current() ? loginWithGoogle(idToken) : null;
  }), [signIn]);
  const signInWithApple = useCallback(() => signIn(async (current) => {
    const { idToken, name, nonce } = await signInWithAppleCredentials();
    return current() ? loginWithApple(idToken, name, nonce) : null;
  }), [signIn]);
  const signInWithDev = useCallback(() => signIn(() => loginWithDev()), [signIn]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (ignoreUnauthorizedRef.current) return;
      void signOut().catch(() => {
        console.warn("[auth] could not clear saved credentials");
      });
    });
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  useEffect(() => {
    setTokenRefreshHandler((accessToken, refreshedUser) => {
      if (!mountedRef.current) return;
      // The transport only emits after a current-generation secure write.
      // Ignore an impossible identity mismatch rather than merge accounts.
      if (userRef.current && refreshedUser && userRef.current.id !== refreshedUser.id) return;
      setCurrentToken(accessToken);
      if (refreshedUser) {
        setProfileValidated(true);
        setCurrentUser((previous) => previous ? { ...previous, ...refreshedUser } : refreshedUser);
      }
    });
    return () => setTokenRefreshHandler(null);
  }, [setCurrentToken, setCurrentUser]);

  useEffect(() => {
    if (user?.locale) void ensureLocale(user.locale);
  }, [user?.locale]);

  // Cached display fields intentionally omit preferences. Running bootstrap
  // on those defaults would unregister push and overwrite local reminders.
  useBootstrapSync({
    token: profileValidated ? token : null,
    user: profileValidated ? user : null,
    setUser: setCurrentUser,
  });

  // Capturing the render's generation also fences callbacks retained by a
  // dismissed screen, including a fast account A → B → A transition.
  const sessionGeneration = getSessionGeneration();
  const refreshUser = useCallback(async (read: (token: string) => Promise<User> = api.me) => {
    if (!token || !isCurrent(sessionGeneration)) return;
    const revision = updateUserGenRef.current;
    const me = await read(token);
    if (!isCurrent(sessionGeneration) || revision !== updateUserGenRef.current) return;
    setCurrentUser(me);
    setProfileValidated(true);
    void writeCachedUser(me);
  }, [token, sessionGeneration, isCurrent, setCurrentUser]);

  const completeOnboarding = useCallback(async () => {
    if (!isCurrent(sessionGeneration)) return;
    await setOnboarded();
    if (isCurrent(sessionGeneration)) setOnboardedState(true);
  }, [sessionGeneration, isCurrent]);

  const updateUser = useCallback(async (patch: Partial<User>) => {
    if (!token || !isCurrent(sessionGeneration)) return;
    const revision = ++updateUserGenRef.current;
    const snapshot = userRef.current;
    const snapshotValidated = profileValidated;
    setCurrentUser((previous) => previous ? { ...previous, ...patch } : previous);
    try {
      const updated = await api.updateMe(token, patch);
      if (!isCurrent(sessionGeneration) || revision !== updateUserGenRef.current) return;
      setCurrentUser(updated);
      setProfileValidated(true);
      void writeCachedUser(updated);
      // Saved now: what the server derives from them (a to-do's notify_at) may read again.
      const fields = (Object.keys(patch) as (keyof User)[]).filter((field) => snapshot?.[field] !== updated[field]);
      if (fields.length) emitAppEvent("userUpdated", { fields });
    } catch {
      if (!isCurrent(sessionGeneration) || revision !== updateUserGenRef.current) return;
      setCurrentUser(snapshot);
      setProfileValidated(snapshotValidated);
      throw new Error("update failed");
    }
  }, [token, sessionGeneration, profileValidated, isCurrent, setCurrentUser]);

  const mergeUser = useCallback((patch: Partial<User>) => {
    if (!isCurrent(sessionGeneration)) return;
    ++updateUserGenRef.current;
    setCurrentUser((previous) => previous ? { ...previous, ...patch } : previous);
  }, [sessionGeneration, isCurrent, setCurrentUser]);

  // The server refused a chat turn, voice or a photo read for want of consent
  // (withdrawn on another device, say): the root layout's gate asks again.
  useEffect(() => {
    setConsentRequiredHandler(() => mergeUser({ ai_data_consent_at: null }));
    return () => setConsentRequiredHandler(null);
  }, [mergeUser]);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      profileValidated,
      signInWithGoogle,
      signInWithApple,
      signInWithDev,
      signOut,
      refreshUser,
      updateUser,
      mergeUser,
      onboarded,
      completeOnboarding,
      setIgnoreUnauthorized,
    }),
    [
      user,
      token,
      loading,
      profileValidated,
      signInWithGoogle,
      signInWithApple,
      signInWithDev,
      signOut,
      refreshUser,
      updateUser,
      mergeUser,
      onboarded,
      completeOnboarding,
      setIgnoreUnauthorized,
    ],
  );

  const tokenBag = useMemo(() => ({ token }), [token]);
  const readUser = useCallback(() => userRef.current, []);
  // Not `getToken`: that name is the stored-credential reader startup uses.
  const latestToken = useCallback(() => tokenRef.current, []);
  const account = token && user ? `${user.id}:${sessionGeneration}` : null;
  const accountSession = useMemo(
    () => ({ account, getToken: latestToken }),
    [account, latestToken],
  );

  return (
    <AuthTokenContext.Provider value={tokenBag}>
      <AccountSessionContext.Provider value={accountSession}>
        <AuthUserReaderContext.Provider value={readUser}>
          <AuthContext.Provider value={value}>
            {loading || startupFailed
              ? <AuthLoadingShell failed={startupFailed} onRetry={retryStartup} onSignOut={signOutFromLaunch} />
              : children}
          </AuthContext.Provider>
        </AuthUserReaderContext.Provider>
      </AccountSessionContext.Provider>
    </AuthTokenContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

/** Prefer this in FlashList / message rows that only need the bearer token. */
export function useAuthToken(): string | null {
  const bag = useContext(AuthTokenContext);
  if (!bag) {
    throw new Error("useAuthToken must be used within AuthProvider");
  }
  return bag.token;
}

/**
 * The signed-in user as of the moment it is called. For a handler in a list
 * row that needs the plan or locale on press: unlike `useAuth()`, it never
 * re-renders the row when the profile or quota is patched.
 */
export function useAuthUserReader(): () => User | null {
  const read = useContext(AuthUserReaderContext);
  if (!read) {
    throw new Error("useAuthUserReader must be used within AuthProvider");
  }
  return read;
}

export function useAuthOptional() {
  return useContext(AuthContext);
}
