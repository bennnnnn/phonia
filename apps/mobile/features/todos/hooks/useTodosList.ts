import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { api, type Todo } from "@/lib/api";
import { getSessionGeneration, requireTokenSession } from "@/lib/auth";
import { isContextFresh } from "@/lib/cache/contextRefresh";
import { useOnForeground } from "@/lib/foregroundRefresh";
import { zoneReportSettled } from "@/lib/zoneReport";
import { getTodoMutationState, type TodoMutationState } from "@/features/todos/model/todoMutationState";

type TodosRefreshOptions = { silent?: boolean; force?: boolean; afterPending?: boolean };
type Update = (rows: Todo[]) => Todo[];
type Pending = { task: Promise<void>; updates: Update[] };

function waitForMutations(state: TodoMutationState, signal: AbortSignal): Promise<void> {
  if (!state.pendingIds.size || signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const changed = () => {
      if (state.pendingIds.size && !signal.aborted) return;
      state.listeners.delete(changed);
      signal.removeEventListener("abort", changed);
      resolve();
    };
    state.listeners.add(changed);
    signal.addEventListener("abort", changed);
    changed();
  });
}

function createResource(owner: { session: number; signedIn: boolean; userId?: string }) {
  return { owner, data: [] as Todo[], loaded: false,
    retainedOpenIds: undefined as Set<string> | undefined,
    fetchedAt: undefined as number | undefined, pending: undefined as Pending | undefined,
    controller: new AbortController(),
    // Completed to-dos from before the last 30 days: left out until the user asks (NET-16).
    olderCompleted: false, allCompleted: false };
}

/** One full list per account session; mutations replay over a read already in flight. */
export function useTodosList(token: string | null | undefined, userId: string | undefined) {
  const session = getSessionGeneration();
  const signedIn = Boolean(token && userId);
  const owner = useMemo(() => ({ session, signedIn, userId }), [session, signedIn, userId]);
  const resource = useRef(createResource(owner));
  if (resource.current.owner !== owner) resource.current = createResource(owner);
  const currentOwner = useRef(owner);
  currentOwner.current = owner;
  const accessToken = useRef(token);
  accessToken.current = token;
  const mounted = useRef(true);
  useEffect(() => {
    const cache = resource.current;
    if (cache.controller.signal.aborted) cache.controller = new AbortController();
    mounted.current = true;
    return () => { mounted.current = false; cache.controller.abort(); cache.pending = undefined; };
  }, [owner]);
  const initial = { owner, todos: resource.current.data, loading: signedIn && !resource.current.loaded,
    error: false, loaded: resource.current.loaded, retainedOpenIds: resource.current.retainedOpenIds,
    olderCompleted: resource.current.olderCompleted && !resource.current.allCompleted };
  const [state, setState] = useState(initial);
  const view = state.owner === owner ? state : initial;
  const isCurrentSession = useCallback(() => mounted.current && owner.signedIn &&
    currentOwner.current === owner && getSessionGeneration() === owner.session, [owner]);
  const publish = useCallback((patch: { loading?: boolean; error?: boolean } = {}) => {
    if (!isCurrentSession()) return;
    setState((previous) => !isCurrentSession() ? previous : ({
      ...(previous.owner === owner ? previous : { loading: owner.signedIn, error: false }),
      owner, todos: resource.current.data, loaded: resource.current.loaded,
      retainedOpenIds: resource.current.retainedOpenIds,
      olderCompleted: resource.current.olderCompleted && !resource.current.allCompleted, ...patch,
    }));
  }, [isCurrentSession, owner]);
  const getTodos = useCallback(() => isCurrentSession() ? resource.current.data : [], [isCurrentSession]);
  /** When this session's list last came from the server. */
  const readTodosAt = useCallback(() => isCurrentSession() ? resource.current.fetchedAt : undefined, [isCurrentSession]);
  const setTodos = useCallback((action: SetStateAction<Todo[]>) => {
    if (!isCurrentSession()) return;
    const cache = resource.current;
    const update = typeof action === "function" ? action : () => action;
    cache.data = update(cache.data);
    cache.pending?.updates.push(update);
    publish();
  }, [isCurrentSession, publish]);

  const refresh = useCallback(async (opts?: TodosRefreshOptions): Promise<void> => {
    if (!isCurrentSession()) return;
    const cache = resource.current;
    if (opts?.afterPending && cache.pending) await cache.pending.task;
    if (!isCurrentSession()) return;
    const mutations = getTodoMutationState(`${owner.session}:${owner.userId ?? ""}`);
    if (mutations.pendingIds.size) await waitForMutations(mutations, cache.controller.signal);
    if (!isCurrentSession()) return;
    const currentToken = accessToken.current;
    if (!currentToken) return;
    try { requireTokenSession(currentToken); } catch { return; }
    if (!opts?.force && !opts?.afterPending && cache.loaded && isContextFresh(cache.fetchedAt)) {
      publish({ loading: false });
      return;
    }
    if (cache.pending) return cache.pending.task;
    publish({ error: false, ...(!opts?.silent && !cache.loaded ? { loading: true } : {}) });
    const pending: Pending = { task: Promise.resolve(), updates: [] };
    cache.pending = pending;
    pending.task = (async () => {
      try {
        const { todos: incoming, olderCompleted } = await api.listTodos(currentToken, {
          signal: cache.controller.signal,
          allCompleted: cache.allCompleted,
        });
        if (!isCurrentSession() || cache.pending !== pending) return;
        cache.olderCompleted = olderCompleted;
        cache.data = pending.updates.reduce((rows, update) => update(rows), incoming);
        // An optimistic completion/removal must not erase persisted seen state.
        cache.retainedOpenIds = new Set([...incoming, ...cache.data]
          .filter((row) => !row.checked).map((row) => row.id));
        cache.loaded = true;
        cache.fetchedAt = Date.now();
        publish({ loading: false, error: false });
      } catch {
        if (cache.pending === pending) publish({ loading: false, error: true });
      } finally {
        if (cache.pending === pending) cache.pending = undefined;
      }
    })();
    return pending.task;
  }, [isCurrentSession, owner, publish]);

  /** Read the completed to-dos the list left out (older than 30 days), for this session. */
  const showOlderCompleted = useCallback(async () => {
    if (!isCurrentSession() || resource.current.allCompleted) return;
    resource.current.allCompleted = true;
    await refresh({ force: true, afterPending: true });
  }, [isCurrentSession, refresh]);

  useEffect(() => { void refresh(); }, [refresh]);
  // Read again past FOREGROUND_STALE_MS.todos (the 20 s isContextFresh window), once the
  // zone report the same return started has landed: its read (userUpdated) is this one.
  useOnForeground(() => void zoneReportSettled().then(() => refresh({ silent: true })), signedIn);
  return { todos: view.todos, loading: view.loading, error: view.error, loaded: view.loaded,
    retainedOpenIds: view.retainedOpenIds, olderCompleted: view.olderCompleted, showOlderCompleted,
    setTodos, getTodos, readTodosAt, refresh, isCurrentSession };
}
