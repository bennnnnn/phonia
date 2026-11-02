import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAuthOptional } from "@/contexts/AuthContext";
import { useAccountSession } from "@/contexts/accountSession";
import { api, type ModelInfo } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { readCachedModels, writeCachedModels } from "@/lib/cachedModels";
import { MODEL_CATALOG_FALLBACK } from "@/lib/modelCatalogFallback";
import { shouldRefreshModels } from "@/lib/modelRefresh";
import { FOREGROUND_STALE_MS, useOnForeground } from "@/lib/foregroundRefresh";
import { hasPlanFeature } from "@/lib/plan";

const AUTO_MODEL_ID = "auto";

const MODEL_REFRESH_TTL_MS = FOREGROUND_STALE_MS.models;

function defaultModelPreferences(
  models: ModelInfo[],
  isPaid: boolean,
): string[] {
  const ids = models
    .filter((m) => m.available && (isPaid || m.plan_access === "free"))
    .map((m) => m.id);
  return [AUTO_MODEL_ID, ...ids];
}

export function buildModelPreferences(
  auto: boolean,
  modelIds: Iterable<string>,
): string[] {
  const ids = [...modelIds];
  return auto ? [AUTO_MODEL_ID, ...ids] : ids;
}

type ModelsContextValue = {
  models: ModelInfo[];
  loading: boolean;
  refresh: () => Promise<void>;
  labelFor: (id: string | null | undefined) => string;
  isPaid: boolean;
  autoEnabled: boolean;
  modelEnabledSet: Set<string>;
  enabledSet: Set<string>;
  preferences: string[];
  AUTO_MODEL_ID: string;
};

const ModelsContext = createContext<ModelsContextValue | null>(null);

/** A catalog belongs to the account that fetched it, so after signout or an
 * account switch the list falls back at once instead of showing the last one. */
type AccountCatalog = { userId: string; models: ModelInfo[] };

export function ModelsProvider({ children }: { children: ReactNode }) {
  const auth = useAuthOptional();
  // Keyed on the account: the hourly token rotation re-read /models (code-health audit NET-11).
  const { account, getToken } = useAccountSession();
  const user = auth?.user;
  const userId = user?.id;
  const [catalog, setCatalog] = useState<AccountCatalog | null>(null);
  const models =
    catalog && catalog.userId === userId ? catalog.models : MODEL_CATALOG_FALLBACK;
  const [loading, setLoading] = useState(false);
  const inflightRef = useRef<Promise<void> | null>(null);
  const lastFetchedAtRef = useRef<number>(0);

  // Paint the last catalog this account fetched, unless /models already answered.
  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    void readCachedModels(userId).then((cached) => {
      if (cancelled || !cached) return;
      setCatalog((current) =>
        current?.userId === userId ? current : { userId, models: cached },
      );
    });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!account || !token || !userId) return;
    if (inflightRef.current) {
      await inflightRef.current;
      return;
    }
    setLoading(true);
    const session = getSessionGeneration();
    const task = (async () => {
      try {
        const fetched = await api.listModels(token);
        // A list that lands after signout is neither shown nor kept.
        if (session !== getSessionGeneration()) return;
        if (fetched.length > 0) {
          setCatalog({ userId, models: fetched });
          void writeCachedModels(userId, fetched);
        }
        lastFetchedAtRef.current = Date.now();
      } catch {
        /* keep the cached or fallback list */
      } finally {
        setLoading(false);
      }
    })();
    inflightRef.current = task;
    try {
      await task;
    } finally {
      inflightRef.current = null;
    }
  }, [account, getToken, userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useOnForeground(() => {
    if (shouldRefreshModels(lastFetchedAtRef.current, Date.now(), MODEL_REFRESH_TTL_MS)) void refresh();
  }, Boolean(account));

  // Paid plans (Plus and Pro) unlock every model; the server enforces it.
  const isPaid = hasPlanFeature(user, "all_models");

  const preferences = useMemo(
    () => user?.enabled_models ?? defaultModelPreferences(models, isPaid),
    [user?.enabled_models, models, isPaid],
  );

  const autoEnabled = preferences.includes(AUTO_MODEL_ID);

  // "Auto" saved alone (no models listed) uses the plan's default models, so
  // those are the ones switched on: every switch showed off while Auto used them.
  const modelEnabledSet = useMemo(() => {
    const chosen = preferences.filter((id) => id !== AUTO_MODEL_ID);
    const ids = chosen.length
      ? chosen
      : defaultModelPreferences(models, isPaid).filter((id) => id !== AUTO_MODEL_ID);
    return new Set(ids);
  }, [preferences, models, isPaid]);

  const labelFor = useCallback(
    (id: string | null | undefined) => {
      if (!id) return "";
      return models.find((model) => model.id === id)?.label ?? id;
    },
    [models],
  );

  const value = useMemo(
    () => ({
      models,
      loading,
      refresh,
      labelFor,
      isPaid,
      autoEnabled,
      modelEnabledSet,
      enabledSet: modelEnabledSet,
      preferences,
      AUTO_MODEL_ID,
    }),
    [
      models,
      loading,
      refresh,
      labelFor,
      isPaid,
      autoEnabled,
      modelEnabledSet,
      preferences,
    ],
  );

  return (
    <ModelsContext.Provider value={value}>{children}</ModelsContext.Provider>
  );
}

export function useModelsContext() {
  const ctx = useContext(ModelsContext);
  if (!ctx) {
    throw new Error("useModelsContext must be used within ModelsProvider");
  }
  return ctx;
}
