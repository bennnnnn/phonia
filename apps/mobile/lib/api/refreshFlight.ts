/**
 * The one refresh of a refresh token in flight, shared by everything in this JS runtime.
 *
 * The server rotates the token on every refresh, so a second refresh of the same token is a
 * second rotation the phone can lose. `lib/api/client.ts` already shares one refresh among its
 * callers, but in that module's own variables: a second copy of the module (Fast Refresh
 * running it again, a bundle or test that loads it twice) started a refresh of its own. This
 * registry lives on `globalThis` and is keyed by the refresh token itself, so every copy that
 * reads the same stored token joins the one request. A JS reload starts a new runtime, which
 * no registry survives: the server answers that retry within its rotation grace
 * (apps/api/app/modules/account/tokens.py).
 */

type Flights = Map<string, Promise<unknown>>;

const FLIGHTS = Symbol.for("phonia.refreshFlights");

function flights(): Flights {
  const holder = globalThis as typeof globalThis & { [FLIGHTS]?: Flights };
  holder[FLIGHTS] ??= new Map();
  return holder[FLIGHTS];
}

/**
 * The refresh of `refreshToken` already in flight, or the one `start` begins. `signal` is the
 * starter's deadline: once it fires the flight is let go, so a stalled one never holds the
 * next refresh (each caller that joined it still fails at its own deadline).
 */
export function shareRefresh<T>(refreshToken: string, signal: AbortSignal, start: () => Promise<T>): Promise<T> {
  const inFlight = flights();
  const joined = inFlight.get(refreshToken);
  if (joined) return joined as Promise<T>;
  const flight = start();
  inFlight.set(refreshToken, flight);
  const release = () => {
    if (inFlight.get(refreshToken) === flight) inFlight.delete(refreshToken);
  };
  flight.then(release, release);
  signal.addEventListener("abort", release, { once: true });
  return flight;
}
