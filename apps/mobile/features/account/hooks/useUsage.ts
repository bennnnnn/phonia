import { useCallback, useEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";

import { useAccountSession } from "@/contexts/accountSession";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import type { Usage } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import {
  fetchTodayUsage,
  getCachedUsage,
  invalidateUsageCache,
  usageReadAt,
} from "@/lib/cache/usageCache";
import { useOnForeground } from "@/lib/foregroundRefresh";

type UsageState = {
  account: string | null;
  generation: number;
  usage: Usage | null;
  loading: boolean;
  error: boolean;
};

/** A kept value is shown only on the UTC day the server counted it for (`usage/today`). */
function todayUsage(usage: Usage | null | undefined): Usage | null {
  return usage?.date === new Date().toISOString().slice(0, 10) ? usage : null;
}

/** Today's usage, kept per account: the hourly token rotation reads nothing again (NET-11). */
export function useUsage() {
  const { account, getToken } = useAccountSession();
  const generation = getSessionGeneration();
  const accountRef = useRef(account);
  accountRef.current = account;
  const mountedRef = useRef(false);
  const requestRef = useRef(0);
  const [state, setState] = useState<UsageState>(() => ({
    account,
    generation,
    usage: account ? todayUsage(getCachedUsage(account)) : null,
    loading: Boolean(account),
    error: false,
  }));

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestRef.current += 1;
    };
  }, []);

  const refresh = useCallback(async (opts?: { force?: boolean }) => {
    const isCurrent = () =>
      mountedRef.current && accountRef.current === account && generation === getSessionGeneration();
    const token = getToken();
    if (!account || !token || !isCurrent()) return;
    const request = ++requestRef.current;
    const cached = getCachedUsage(account);
    setState((previous) => ({
      account,
      generation,
      usage: previous.account === account && previous.generation === generation
        ? todayUsage(previous.usage)
        : todayUsage(cached),
      loading: true,
      error: false,
    }));
    const data = await fetchTodayUsage(account, token, {
      force: opts?.force || Boolean(cached && !todayUsage(cached)),
    });
    if (!isCurrent() || request !== requestRef.current) return;
    // What /usage/today answered is today's on the server's clock. Checked against the
    // phone's, a clock a minute fast hid it as an error for that minute before each UTC
    // midnight, and Retry asked again for the same answer.
    setState({ account, generation, usage: data, loading: false, error: !data });
  }, [account, generation, getToken]);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  useEffect(() => {
    if (!account) invalidateUsageCache();
  }, [account]);
  // The usage cache reads again past FOREGROUND_STALE_MS.usage.
  useOnForeground(() => void refresh(), Boolean(account));
  // The API back after an outage: read again while the screen has focus, unless a read landed
  // since the connection was lost.
  useReconnectRefresh(() => void refresh(), { readAt: () => (account ? usageReadAt(account) : undefined) });

  const isCurrentState = state.account === account && state.generation === generation;
  return {
    usage: isCurrentState ? state.usage : null,
    loading: isCurrentState ? state.loading : Boolean(account),
    error: isCurrentState && state.error,
    refresh,
  };
}
