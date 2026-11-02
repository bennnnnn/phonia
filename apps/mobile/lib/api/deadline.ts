/**
 * Deadlines for a whole exchange. A fetch's own timer ends when the headers arrive;
 * these also cover the body, a token refresh, and a wait on someone else's work
 * (code-health audit NET-17).
 */
import { isAbortError } from "@/lib/api/abort";

export function abortError(): Error {
  const error = new Error("Request canceled");
  error.name = "AbortError";
  return error;
}

/** `promise`, or an AbortError as soon as `signal` aborts (the work itself runs on). */
export function untilAborted<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(abortError());
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

/**
 * Run `work` under one deadline that covers the whole exchange, the body included.
 * A fetch's own timer ended when the headers arrived, so a body that stalled after
 * them hung its caller for good (code-health audit NET-17). The signal `work` gets
 * aborts at `timeoutMs` or with the caller's, and the result rejects then even if a
 * body read ignores the abort: with `timeoutError()` at the deadline (an AbortError
 * by default, as a fetch timeout gave), with an AbortError when the caller aborts.
 */
export async function withDeadline<T>(
  timeoutMs: number,
  callerSignal: AbortSignal | null | undefined,
  work: (signal: AbortSignal) => Promise<T>,
  timeoutError: () => Error = abortError,
): Promise<T> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ended = new Promise<never>((_resolve, reject) => {
    controller.signal.addEventListener("abort", () => reject(abortError()), { once: true });
    timer = setTimeout(() => {
      reject(timeoutError());
      controller.abort();
    }, timeoutMs);
  });
  callerSignal?.addEventListener("abort", forwardAbort, { once: true });
  if (callerSignal?.aborted) controller.abort();
  try {
    return await Promise.race([work(controller.signal), ended]);
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", forwardAbort);
  }
}

const UNREACHABLE = "ServerUnreachableError";

/** What a caller is told when the server could not be reached in time. Its English is
 * for logs: a screen words it in the phone's language (`isServerUnreachable`). */
export function serverUnreachableError(): Error {
  const error = new Error("Could not reach the Recall server. Check your connection and try again.");
  error.name = UNREACHABLE;
  return error;
}

/** fetch's own failure with no answer, however the runtime words it. */
const NO_ANSWER = /network request failed|failed to fetch|network error/i;

/**
 * Recall gave no answer: offline or a dropped connection (fetch's own failure), or past a
 * deadline (`serverUnreachableError`, a timeout's AbortError). A caller that cancels its
 * own request checks for that first. A refusal the API answered (it has a `status`) is
 * never this. The English of each showed as it came in a Library toast and on a picture card.
 */
export function isServerUnreachable(error: unknown): boolean {
  if (isAbortError(error)) return true;
  if (!(error instanceof Error) || "status" in error) return false;
  return error.name === UNREACHABLE || NO_ANSWER.test(error.message);
}
