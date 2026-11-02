import { isAbortError } from "@/lib/api/abort";
import { getSessionGeneration, requireTokenSession, SessionChangedError } from "@/lib/auth";
import { StaleResourceCache } from "@/lib/cache/staleResource";

/** A read's outcome. A failure says so, and still hands back what was cached. */
export type ResourceResult<T> =
  | { data: T; error: null }
  | { data: T | null; error: Error };

/** A pure local edit; it is replayed over any read already running. */
export type ResourceUpdate<T> = (current: T) => T;

/** Shows the user a failed read that would otherwise go unseen. */
export type FailureReporter = (error: Error) => void;

type ResourceFetchOptions = {
  /** Skip the freshness window. A read already running is still joined. */
  force?: boolean;
  /** Let the running read (and the edits replayed over it) land, then read again. */
  afterPending?: boolean;
  /** Told about an unexpected failure while older data stays on screen. */
  report?: FailureReporter;
};

type CacheOptions<T, S> = {
  staleMs: number;
  /** Keep at most this many keys, dropping the least recently used. */
  maxEntries?: number;
  /** The value a local edit starts from before the first read; without it, such edits wait for one. */
  empty?: () => T;
  /** Extra state that lives and dies with one account's cache (created chat, deleted ids). */
  sessionState: () => S;
};

/** Local edits made before the first read are kept but never count as fresh. */
const NEVER_FETCHED = Number.NEGATIVE_INFINITY;
const NETWORK_FAILURE = /network request failed|failed to fetch|network error|could not reach|timed? ?out/i;

export function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught));
}

/**
 * Failures the user already hears about elsewhere: offline or timed out (the
 * offline banner), and a sign-in that ended or changed (the app signs out).
 */
export function isExpectedReadFailure(error: Error): boolean {
  if (isAbortError(error) || error.name === "SessionChangedError") return true;
  if ("status" in error) return error.status === 401;
  return NETWORK_FAILURE.test(error.message);
}

/** What a read gets when sign-out or an account switch overtook it. */
export function sessionChanged<T>(): ResourceResult<T> {
  return { data: null, error: new SessionChangedError() };
}

class PendingRead<T> {
  readonly updates: ResourceUpdate<T>[] = [];
  readonly task: Promise<ResourceResult<T>>;
  report: FailureReporter | undefined;

  constructor(run: (read: PendingRead<T>) => Promise<ResourceResult<T>>, report?: FailureReporter) {
    this.report = report;
    this.task = run(this);
  }

  replay(loaded: T): T {
    return this.updates.reduce((value, update) => update(value), loaded);
  }
}

type Owner<Key, T, S> = {
  session: number;
  entries: StaleResourceCache<Key, T>;
  reads: Map<Key, PendingRead<T>>;
  /** Keys whose current failure streak was already reported. */
  reported: Set<Key>;
  state: S;
};

/**
 * One account's cached reads. Sign-out or an account switch (a new session
 * generation) and `invalidate()` replace the owner, so a read started before
 * either can never land after it. Reads of one key share a single request,
 * edits made while it runs are replayed over its result in the same step that
 * stores it, and a failed read returns `{ data: previous ?? null, error }`.
 *
 * Built on `StaleResourceCache` for values and timestamps. It keeps its own
 * read records because the fence check, the replay and the store must happen
 * in one step: `StaleResourceCache.fetch` stores a value a tick after its
 * loader resolves, and an edit made in that tick would be lost.
 */
export class SessionResourceCache<Key, T, S = undefined> {
  private owner: Owner<Key, T, S>;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly options: CacheOptions<T, S>) {
    // Session -1: the first access adopts the current account without reading
    // it at import time.
    this.owner = this.newOwner(-1);
  }

  get(key: Key): T | undefined {
    return this.current().entries.get(key);
  }

  fetchedAt(key: Key): number | undefined {
    const at = this.current().entries.getFetchedAt(key);
    return at === undefined || at === NEVER_FETCHED ? undefined : at;
  }

  isFresh(key: Key): boolean {
    return this.current().entries.isFresh(key);
  }

  /** The read of `key` now running, if any. */
  inflight(key: Key): Promise<ResourceResult<T>> | undefined {
    return this.current().reads.get(key)?.task;
  }

  state(): S {
    return this.current().state;
  }

  /** A check that stays true until sign-out, an account switch or `invalidate()`. */
  lease(): () => boolean {
    const owner = this.current();
    return () => this.holds(owner);
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /** Store a complete value, unless the account changed since `expectedSession`. */
  set(key: Key, data: T, expectedSession?: number): boolean {
    const owner = this.current();
    if (expectedSession !== undefined && owner.session !== expectedSession) return false;
    owner.entries.set(key, data);
    owner.reads.get(key)?.updates.push(() => data);
    this.notify();
    return true;
  }

  /**
   * A value restored from disk for a key nothing has read or edited this
   * session: shown at once, never fresh, and never replayed over a running
   * read, whose result replaces it.
   */
  seed(key: Key, data: T, expectedSession: number): boolean {
    const owner = this.current();
    if (owner.session !== expectedSession || owner.entries.getEntry(key) !== undefined) return false;
    owner.entries.set(key, data, NEVER_FETCHED);
    this.notify();
    return true;
  }

  /** Apply a local edit now and over the running read. Returns the edited value, if any. */
  update(key: Key, update: ResourceUpdate<T>, expectedSession?: number): T | undefined {
    const owner = this.current();
    if (expectedSession !== undefined && owner.session !== expectedSession) return undefined;
    owner.reads.get(key)?.updates.push(update);
    const entry = owner.entries.getEntry(key);
    const base = entry ? entry.data : this.options.empty?.();
    if (base === undefined) return undefined;
    const data = owner.entries.set(key, update(base), entry?.fetchedAt ?? NEVER_FETCHED);
    this.notify();
    return data;
  }

  updateEach(update: ResourceUpdate<T>): void {
    const owner = this.current();
    owner.entries.updateEach(update);
    owner.reads.forEach((read) => read.updates.push(update));
    this.notify();
  }

  /** Drop everything; reads already running can no longer land. */
  invalidate(): void {
    this.owner = this.newOwner(getSessionGeneration());
    this.notify();
  }

  async fetch(
    key: Key,
    token: string,
    load: () => Promise<T>,
    options: ResourceFetchOptions = {},
  ): Promise<ResourceResult<T>> {
    try {
      requireTokenSession(token);
    } catch (caught) {
      return { data: null, error: asError(caught) };
    }
    const owner = this.current();
    const running = owner.reads.get(key);
    if (options.afterPending && running) {
      // Recovery after a failed edit must not reuse a read carrying its rollback.
      await running.task;
      if (!this.holds(owner)) return sessionChanged();
      return this.fetch(key, token, load, { ...options, afterPending: false, force: true });
    }
    const fresh = owner.entries.isFresh(key) ? owner.entries.get(key) : undefined;
    if (!options.force && !options.afterPending && fresh !== undefined) {
      return { data: fresh, error: null };
    }
    if (running) {
      running.report ??= options.report;
      return running.task;
    }
    const read = new PendingRead<T>((self) => this.run(owner, key, self, load), options.report);
    owner.reads.set(key, read);
    return read.task;
  }

  private async run(
    owner: Owner<Key, T, S>,
    key: Key,
    read: PendingRead<T>,
    load: () => Promise<T>,
  ): Promise<ResourceResult<T>> {
    let loaded: T;
    try {
      // load() starts now; even a synchronous throw settles after fetch() registered this read.
      loaded = await new Promise<T>((resolve) => { resolve(load()); });
    } catch (caught) {
      return this.fail(owner, key, read, asError(caught));
    }
    if (!this.holds(owner)) return sessionChanged();
    owner.reads.delete(key);
    owner.reported.delete(key);
    const data = owner.entries.set(key, read.replay(loaded));
    this.notify();
    return { data, error: null };
  }

  private fail(
    owner: Owner<Key, T, S>,
    key: Key,
    read: PendingRead<T>,
    error: Error,
  ): ResourceResult<T> {
    if (!this.holds(owner)) return sessionChanged();
    owner.reads.delete(key);
    const previous = owner.entries.get(key) ?? null;
    // With nothing cached, the screen's error state says so; a warning would repeat it.
    if (previous !== null && read.report && !isExpectedReadFailure(error) && !owner.reported.has(key)) {
      owner.reported.add(key);
      read.report(error);
    }
    return { data: previous, error };
  }

  private holds(owner: Owner<Key, T, S>): boolean {
    return this.owner === owner && owner.session === getSessionGeneration();
  }

  /** Reads can run during React render: drop the previous account quietly here. */
  private current(): Owner<Key, T, S> {
    const session = getSessionGeneration();
    if (this.owner.session !== session) this.owner = this.newOwner(session);
    return this.owner;
  }

  private newOwner(session: number): Owner<Key, T, S> {
    return {
      session,
      entries: new StaleResourceCache<Key, T>(this.options.staleMs, this.options.maxEntries),
      reads: new Map(),
      reported: new Set(),
      state: this.options.sessionState(),
    };
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener());
  }
}
