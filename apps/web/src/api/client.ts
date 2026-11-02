import type { AuthResult } from "@/api/types";

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

class ApiRequestError extends Error {
  readonly status: number;
  constructor(status: number, body: string) {
    super(body || `Request failed: ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

const AUTH_TIMEOUT_MS = 15_000;
const CSRF_KEY = "recall.csrf";

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs = AUTH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal, credentials: "include" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Could not reach the Recall API. Is it running?", { cause: error });
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

/** Access lives in memory; refresh is an httpOnly cookie; CSRF is session-scoped. */
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

function getCsrfToken(): string | null {
  try {
    return sessionStorage.getItem(CSRF_KEY);
  } catch {
    return null;
  }
}

export function setAccessSession(access: string, csrf?: string | null): void {
  accessToken = access;
  if (csrf) {
    try {
      sessionStorage.setItem(CSRF_KEY, csrf);
    } catch {
      /* private mode */
    }
  }
}

export function clearTokens(): void {
  accessToken = null;
  try {
    sessionStorage.removeItem(CSRF_KEY);
  } catch {
    /* ignore */
  }
}

export function csrfHeaders(): Record<string, string> {
  const csrf = getCsrfToken();
  return csrf ? { "X-CSRF-Token": csrf } : {};
}

let refreshInFlight: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const response = await fetchWithTimeout(apiUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...csrfHeaders() },
        body: JSON.stringify({}),
      });
      if (!response.ok) return null;
      const data = (await response.json()) as AuthResult;
      setAccessSession(data.access_token, data.csrf_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function request<T>(
  path: string,
  token: string,
  init?: RequestInit,
  allowRefresh = true,
  timeoutMs = 30_000,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = init?.signal ?? null;
  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort);
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      signal: controller.signal,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...csrfHeaders(),
        ...(init?.headers ?? {}),
      },
    });
    if (response.status === 401 && allowRefresh) {
      const refreshed = await refreshAccessToken();
      if (refreshed) return request<T>(path, refreshed, init, false);
      clearTokens();
      const text = await response.text();
      throw new ApiRequestError(response.status, text);
    }
    if (!response.ok) {
      const text = await response.text();
      throw new ApiRequestError(response.status, text);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } finally {
    externalSignal?.removeEventListener("abort", onExternalAbort);
    clearTimeout(timeout);
  }
}

export async function requestRaw(
  path: string,
  token: string,
  init: RequestInit,
  allowRefresh = true,
  timeoutMs = 30_000,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = init.signal ?? null;
  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort);
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      signal: controller.signal,
      credentials: "include",
      headers: {
        Authorization: `Bearer ${token}`,
        ...csrfHeaders(),
        ...init.headers,
      },
    });
    if (response.status === 401 && allowRefresh) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return requestRaw(path, refreshed, init, false);
      }
      clearTokens();
    }
    return response;
  } finally {
    externalSignal?.removeEventListener("abort", onExternalAbort);
    clearTimeout(timeout);
  }
}

export { fetchWithTimeout };
